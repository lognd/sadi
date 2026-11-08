"""Runner tests: dependency order, parallelism, timeouts and deterministic result order."""

# frob:ticket 01M6WJHW2KET2M1730MZVJ1X4E
from __future__ import annotations

import threading
from collections.abc import Mapping

import pytest
from doctor_fakes import healthy

import sadi.doctor as doctor
from sadi.doctor import registry
from sadi.doctor.runner import Budget, schedule
from sadi.doctor.schema import RunOptions, SkipReason, Status

TINY = Budget(check_timeout_s=0.05, run_timeout_s=5.0, workers=4)


def _go(order, deps, work, budget=None, gate=None):
    """Call schedule with string results and a no-op gate unless one is given."""
    return schedule(
        order,
        deps,
        work,
        gate or (lambda i, d: None),
        lambda i, why: f"abort:{why}",
        budget or Budget(),
    )


# frob:tests python/sadi/doctor/runner.py::schedule
# frob:tests python/tests/doctor/test_runner.py::test_dependencies_run_first
def test_dependencies_run_first() -> None:
    """A dependent starts only after its prerequisite finished, even with idle workers."""
    log: list[str] = []
    lock = threading.Lock()

    def work(i: str) -> str:
        with lock:
            log.append(i)
        return i

    out = _go(["b", "a"], {"b": ("a",)}, work)
    assert set(out) == {"a", "b"}
    assert log == ["a", "b"]


# frob:tests python/tests/doctor/test_runner.py::test_independent_checks_overlap
def test_independent_checks_overlap() -> None:
    """Independent checks run at the same time: a barrier of N only opens if all N are live."""
    barrier = threading.Barrier(3, timeout=2)
    out = _go(["a", "b", "c"], {}, lambda i: (barrier.wait(), i)[1])
    assert out == {"a": "a", "b": "b", "c": "c"}


# frob:tests python/tests/doctor/test_runner.py::test_worker_limit_respected
def test_worker_limit_respected() -> None:
    """No more than `workers` checks are live at once."""
    live = 0
    peak = 0
    lock = threading.Lock()

    def work(i: str) -> str:
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        threading.Event().wait(0.01)
        with lock:
            live -= 1
        return i

    _go([str(n) for n in range(8)], {}, work, Budget(workers=2))
    assert peak <= 2


# frob:tests python/tests/doctor/test_runner.py::test_check_timeout_does_not_hang
def test_check_timeout_does_not_hang() -> None:
    """A stuck check is abandoned at its deadline; the others still finish."""
    release = threading.Event()

    def work(i: str) -> str:
        if i == "slow":
            release.wait(5)
        return i

    try:
        out = _go(["slow", "fast"], {}, work, TINY)
    finally:
        release.set()
    assert out["slow"] == "abort:check-timeout"
    assert out["fast"] == "fast"


# frob:tests python/tests/doctor/test_runner.py::test_run_timeout_aborts_rest
def test_run_timeout_aborts_rest() -> None:
    """When the whole-run budget ends, running and not-yet-started checks are aborted."""
    release = threading.Event()
    budget = Budget(check_timeout_s=5.0, run_timeout_s=0.05, workers=1)
    try:
        out = _go(["a", "b"], {}, lambda i: (release.wait(5), i)[1], budget)
    finally:
        release.set()
    assert out == {"a": "abort:run-timeout", "b": "abort:run-timeout"}


# frob:tests python/tests/doctor/test_runner.py::test_worker_crash_is_reported
def test_worker_crash_is_reported() -> None:
    """An exception escaping the work function becomes an aborted result, not a lost check."""

    def work(i: str) -> str:
        raise RuntimeError("boom")

    assert _go(["a"], {}, work) == {"a": "abort:crashed"}


# frob:tests python/tests/doctor/test_runner.py::test_gate_short_circuits
def test_gate_short_circuits() -> None:
    """The gate sees finished prerequisites and can skip the dependent without running it."""
    ran: list[str] = []

    def work(i: str) -> str:
        ran.append(i)
        return "bad" if i == "a" else "ok"

    def gate(i: str, done: Mapping[str, str]) -> str | None:
        return "skipped" if done.get("a") == "bad" else None

    out = _go(["a", "b"], {"b": ("a",)}, work, gate=gate)
    assert out == {"a": "bad", "b": "skipped"}
    assert ran == ["a"]


# frob:tests python/tests/doctor/test_runner.py::test_dependency_cycle_is_a_bug
def test_dependency_cycle_is_a_bug() -> None:
    """A cycle is a programmer error and raises instead of hanging."""
    with pytest.raises(ValueError, match="cycle"):
        _go(["a", "b"], {"a": ("b",), "b": ("a",)}, lambda i: i)


@pytest.fixture
def _stuck_check(monkeypatch: pytest.MonkeyPatch):
    """Replace PLAT-010 with a check that blocks until released; yield the release event."""
    release = threading.Event()
    spec, _fn = next(t for t in registry.all_checks() if t[0].id == "PLAT-010")

    def stuck(ctx: registry.Ctx) -> registry.Outcome:
        release.wait(5)
        return registry.ok("late")

    monkeypatch.setitem(registry._CHECKS, "PLAT-010", (spec, stuck))
    yield release
    release.set()


# frob:tests python/tests/doctor/test_runner.py::test_timed_out_check_is_unverified_with_remedy
def test_timed_out_check_is_unverified_with_remedy(_stuck_check: threading.Event) -> None:
    """The report marks the stuck check skip/timeout with a remedy and keeps catalog order."""
    options = RunOptions(checks=("PLAT-010", "PLAT-030"))
    got = doctor.run(options, healthy(), TINY).unwrap()
    assert [r.id for r in got.results] == ["PLAT-010", "PLAT-030"]
    stuck = got.results[0]
    assert stuck.status is Status.SKIP
    assert stuck.skip_reason is SkipReason.TIMEOUT
    assert stuck.mode == "timeout"
    assert stuck.remediation is not None
    assert stuck.evidence.error is not None and stuck.evidence.error.kind == "timeout"
    assert got.results[1].skip_reason is not SkipReason.TIMEOUT


# frob:tests python/tests/doctor/test_runner.py::test_full_run_is_deterministic
def test_full_run_is_deterministic() -> None:
    """Two parallel full runs report identical statuses in the same (catalog) order."""
    a = doctor.run(RunOptions(), healthy()).unwrap()
    b = doctor.run(RunOptions(), healthy()).unwrap()
    key = [(r.id, r.status, r.mode, r.skip_reason) for r in a.results]
    assert key == [(r.id, r.status, r.mode, r.skip_reason) for r in b.results]
    assert [r.id for r in a.results] == [s.id for s, _ in registry.all_checks()]
