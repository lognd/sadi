"""Seeded interleaving storms on the deterministic job harness: no deadlock, no lost job."""

# frob:ticket 01M6W7RAY4KTF866Q0Y7B4SZGG
from __future__ import annotations

import os
import random
from collections import Counter
from collections.abc import Generator, Iterator

import pytest
from typani import Err, Ok

from sadi.jobs import JobKey, JobState, ResultState
from sadi.jobs.testing import Interleaver, JobHarness, Step, make_spec
from sadi.logging_setup import get_logger

_log = get_logger("tests.concurrency.interleavings")

SEEDS = range(int(os.environ.get("SADI_CONC_SEEDS", "50")))
KEYS = ("a", "b", "c")
TERMINAL = {JobState.DONE, JobState.CANCELLED, JobState.SUPERSEDED, JobState.FAILED}

Gen = Generator[Step, bool, dict[str, object]]


def _refine(inputs: dict[str, object]) -> Gen:
    """Four refinement steps, then a result tagged with its data version; honours cancel."""
    for i in range(1, 5):
        cancelled = yield Step(fraction=i / 5, partial={"dv": inputs.get("dv")})
        if cancelled:
            return {}
    return {"dv": inputs.get("dv")}


_OPEN: list[JobHarness] = []


@pytest.fixture(autouse=True)
def _close() -> Iterator[None]:
    """Close every harness created by a test."""
    yield
    while _OPEN:
        _OPEN.pop().close()


def _harness(workers: int) -> JobHarness:
    """Build a started harness with the `refine` script registered."""
    h = JobHarness(workers)
    _OPEN.append(h)
    h.register("refine", _refine)
    h.start()
    return h


def _storm(h: JobHarness, seed: int, *, rounds: int, cancel_p: float) -> tuple[list[str], int]:
    """Drive random submits, cancels, clock advances and actor ticks; return (trace, submitted)."""
    rng = random.Random(seed * 7919 + 1)  # noqa: S311 - determinism, not security
    il = Interleaver(h, seed)
    versions = dict.fromkeys(KEYS, 0)
    submitted = 0
    for _ in range(rounds):
        roll = rng.random()
        if roll < 0.35:
            key = rng.choice(KEYS)
            versions[key] += 1
            submitted += 1
            spec = make_spec(submitted, key, "refine", data_version=versions[key], dv=versions[key])
            assert isinstance(h.manager.submit(spec), Ok)
        elif roll < 0.35 + cancel_p:
            h.manager.cancel_key(JobKey(rng.choice(KEYS)))  # Err when nothing is live
        elif roll < 0.6:
            h.advance(rng.choice((0.05, 0.2, 1.0)))
        else:
            assert isinstance(il.tick(), Ok)
    drained = il.run_until_idle()
    assert isinstance(drained, Ok), f"seed {seed}: {drained}"
    h.advance(5.0)
    drained = il.run_until_idle()
    assert isinstance(drained, Ok), f"seed {seed}: {drained}"
    return il.trace, submitted


def _check_invariants(h: JobHarness, submitted: int, seed: int) -> None:
    """Exactly one terminal outcome per job, ordered finals, and an empty manager."""
    counts = Counter(o.job_id.int for o in h.outcomes)
    assert set(counts) == set(range(1, submitted + 1)), f"seed {seed}: missing outcomes"
    assert set(counts.values()) <= {1}, f"seed {seed}: duplicate outcome"
    assert all(o.state in TERMINAL for o in h.outcomes), f"seed {seed}: non-terminal outcome"
    m = h.manager.metrics()
    assert m.queued == 0
    assert m.running == 0
    done_dv: dict[str, int] = {}
    for env in h.envelopes:
        if env.state is ResultState.FINAL:
            prev = done_dv.get(env.key, 0)
            assert env.data_version >= prev, f"seed {seed}: FINAL went backwards for {env.key}"
            done_dv[env.key] = env.data_version


# frob:tests python/tests/concurrency/test_interleavings.py::test_capture_during_refinement
# frob:tests python/sadi/jobs/testing.py::Interleaver.run_until_idle
@pytest.mark.parametrize("seed", SEEDS)
def test_capture_during_refinement(seed: int) -> None:
    """A newer data version arriving mid-refinement never leaves a stale FINAL behind."""
    h = _harness(2)
    il = Interleaver(h, seed)
    rng = random.Random(seed)  # noqa: S311
    n = 0
    for dv in range(1, 6):
        n += 1
        spec = make_spec(n, "a", "refine", data_version=dv, dv=dv)
        assert isinstance(h.manager.submit(spec), Ok)
        for _ in range(rng.randint(0, 6)):
            assert isinstance(il.tick(), Ok)
    assert isinstance(il.run_until_idle(), Ok)
    _check_invariants(h, n, seed)
    finals = [e for e in h.envelopes if e.state is ResultState.FINAL]
    assert finals, f"seed {seed}: no FINAL produced"
    assert finals[-1].data_version == 5


# frob:tests python/tests/concurrency/test_interleavings.py::test_supersede_storm
# frob:tests python/sadi/jobs/manager.py::JobManager.submit
@pytest.mark.parametrize("seed", SEEDS)
def test_supersede_storm(seed: int) -> None:
    """Many versions per key across a small pool: one terminal outcome per job, no deadlock."""
    h = _harness(2)
    _, submitted = _storm(h, seed, rounds=120, cancel_p=0.0)
    _check_invariants(h, submitted, seed)


# frob:tests python/tests/concurrency/test_interleavings.py::test_cancel_storm
# frob:tests python/sadi/jobs/manager.py::JobManager.cancel_key
@pytest.mark.parametrize("seed", SEEDS)
def test_cancel_storm(seed: int) -> None:
    """Cancels interleaved with submits, progress and clock advances never wedge the pool."""
    h = _harness(2)
    _, submitted = _storm(h, seed, rounds=150, cancel_p=0.2)
    _check_invariants(h, submitted, seed)


# frob:tests python/tests/concurrency/test_interleavings.py::test_trace_replays_identically
# frob:tests python/sadi/jobs/testing.py::Interleaver.replay
@pytest.mark.parametrize("seed", range(5))
def test_trace_replays_identically(seed: int) -> None:
    """A recorded trace re-executes to identical outcomes (failures are reproducible)."""
    h = _harness(2)
    il = Interleaver(h, seed)
    for n in range(1, 7):
        spec = make_spec(n, KEYS[n % 3], "refine", data_version=n, dv=n)
        assert isinstance(h.manager.submit(spec), Ok)
    ran = il.run_until_idle()
    assert isinstance(ran, Ok)
    again = _harness(2)
    for n in range(1, 7):
        spec = make_spec(n, KEYS[n % 3], "refine", data_version=n, dv=n)
        assert isinstance(again.manager.submit(spec), Ok)
    assert isinstance(Interleaver.replay(again, il.trace), Ok)
    assert [(o.job_id, o.state) for o in again.outcomes] == [
        (o.job_id, o.state) for o in h.outcomes
    ]
    assert isinstance(Interleaver.replay(_harness(1), ["step:0"]), Err)
