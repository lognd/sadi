"""Deterministic job-logic tests on the fake harness: no processes, threads or sleeps."""

# frob:ticket 01M6WBZ7QYZPJDF6XR283MEEZ0
from __future__ import annotations

from collections.abc import Generator, Iterator
from uuid import UUID

import pytest
from typani import Err, Ok

from sadi.core.errors import JobCode
from sadi.jobs import JobId, JobState, ResultState
from sadi.jobs.testing import Interleaver, JobHarness, Step, make_spec

Gen = Generator[Step, bool, dict[str, object]]


def _three_steps(inputs: dict[str, object]) -> Gen:
    """Three progress points then a result; stops early (returns) when cancelled."""
    for i in (1, 2, 3):
        cancelled = yield Step(fraction=i / 4, partial={"i": i, "dv": inputs.get("dv")})
        if cancelled:
            return {}
    return {"dv": inputs.get("dv")}


def _defiant(inputs: dict[str, object]) -> Gen:
    """Keeps reporting partials after a cancel arrived, then returns."""
    for i in (1, 2, 3):
        yield Step(fraction=i / 4, partial={"i": i, "dv": inputs.get("dv")})
    return {"dv": inputs.get("dv")}


def _stubborn(inputs: dict[str, object]) -> Gen:
    """Ignores cancel forever (never acknowledges)."""
    while True:
        yield Step(fraction=0.1)


def _boom(inputs: dict[str, object]) -> Gen:
    """Raises on first step."""
    yield Step(fraction=0.1)
    raise ValueError("boom")


_OPEN: list[JobHarness] = []


@pytest.fixture(autouse=True)
def _close_harnesses() -> Iterator[None]:
    """Restore the manager's real clock after each test."""
    yield
    while _OPEN:
        _OPEN.pop().close()


def _harness(workers: int = 1) -> JobHarness:
    h = JobHarness(workers)
    _OPEN.append(h)
    h.register("three", _three_steps)
    h.register("defiant", _defiant)
    h.register("stubborn", _stubborn)
    h.register("boom", _boom)
    h.start()
    return h


def _states(h: JobHarness) -> dict[int, JobState]:
    return {o.job_id.int: o.state for o in h.outcomes}


# frob:tests python/sadi/jobs/testing.py::JobHarness.step
# frob:tests python/sadi/jobs/testing.py::JobHarness.start
# frob:tests python/sadi/jobs/testing.py::JobHarness.run_slot
# frob:tests python/sadi/jobs/testing.py::FakeSlot.step
# frob:tests python/sadi/jobs/testing.py::make_spec
def test_step_through_states() -> None:
    h = _harness()
    spec = make_spec(1, task="three", dv=1)
    assert isinstance(h.manager.submit(spec), Ok)
    jid = spec.job_id
    assert h.manager.state_of(JobId(jid)) is JobState.RUNNING
    assert h.step(0) == Ok("started")
    assert h.manager.state_of(JobId(jid)) is JobState.RUNNING
    assert h.step(0) == Ok("progress:0.25")
    assert h.manager.state_of(JobId(jid)) is JobState.PROGRESSING
    assert [e.state for e in h.envelopes] == [ResultState.REFINING]
    assert h.run_slot(0) == Ok(["progress:0.5", "progress:0.75", "done"])
    assert _states(h) == {1: JobState.DONE}
    assert h.envelopes[-1].state is ResultState.FINAL
    assert h.envelopes[-1].value == {"dv": 1}
    assert isinstance(h.live_slot(0).step(), Err)


# frob:tests python/sadi/jobs/testing.py::JobHarness.act
# frob:tests python/sadi/jobs/testing.py::JobHarness.runnable
def test_supersede_queued_never_starts() -> None:
    h = _harness(1)
    first = make_spec(1, key="a", task="three")
    queued = make_spec(2, key="k", task="three", data_version=1)
    newer = make_spec(3, key="k", task="three", data_version=2)
    for s in (first, queued, newer):
        assert isinstance(h.manager.submit(s), Ok)
    assert _states(h) == {2: JobState.SUPERSEDED}
    assert isinstance(h.run_slot(0), Ok)
    assert isinstance(h.run_slot(0), Ok)
    assert _states(h) == {1: JobState.DONE, 2: JobState.SUPERSEDED, 3: JobState.DONE}
    assert h.manager.metrics().superseded_total == 1
    finals = [e for e in h.envelopes if e.state is ResultState.FINAL and e.key == "k"]
    assert [e.data_version for e in finals] == [2]


def test_supersede_progressing_discards_late_partial() -> None:
    h = _harness(2)
    h.manager.submit(make_spec(1, task="defiant", data_version=1, dv=1))
    h.step(1)
    h.step(1)  # started, first partial
    h.manager.submit(make_spec(2, task="three", data_version=2, dv=2))
    assert h.live_slot(1).cancel_requests == [UUID(int=1)]
    stale = [i for i, e in enumerate(h.envelopes) if e.state is ResultState.STALE]
    assert len(stale) == 1
    # the old job still yields a partial after the supersede: it must be dropped
    n = len(h.envelopes)
    h.step(1)
    assert len(h.envelopes) == n
    assert h.manager.metrics().discarded_results >= 1
    h.run_slot(1)
    assert _states(h)[1] is JobState.SUPERSEDED
    h.run_slot(1)
    assert _states(h) == {1: JobState.SUPERSEDED, 2: JobState.DONE}
    after_stale = h.envelopes[stale[0] + 1 :]
    assert all(e.data_version == 2 for e in after_stale)
    assert [e.state for e in after_stale].count(ResultState.FINAL) == 1


# frob:tests python/sadi/jobs/testing.py::JobHarness.advance
# frob:tests python/sadi/jobs/testing.py::FakeClock.advance
# frob:tests python/sadi/jobs/testing.py::FakeSlot.kill
# frob:tests python/sadi/jobs/testing.py::FakeLoop.call_later
def test_unacknowledged_cancel_is_killed_after_grace() -> None:
    h = _harness(1)
    spec = make_spec(1, task="stubborn")
    h.manager.submit(spec)
    h.step(0)
    h.step(0)
    assert isinstance(h.manager.cancel(JobId(spec.job_id)), Ok)
    assert h.advance(0.4) == 0
    assert h.outcomes == []
    old = h.live_slot(0)
    assert h.advance(0.2) == 1
    out = h.outcomes[0]
    assert out.state is JobState.CANCELLED
    assert out.killed
    assert old.killed
    assert h.live_slot(0) is not old
    m = h.manager.metrics()
    assert (m.killed_total, m.worker_restarts) == (1, 1)


# frob:tests python/sadi/jobs/manager.py::JobManager.metrics
# frob:tests python/sadi/jobs/pool.py::WorkerSlot.pending_coalesced
# frob:tests python/sadi/jobs/testing.py::FakeSlot.pending_coalesced
# frob:tests python/sadi/jobs/testing.py::FakeSlot.take_progress
def test_progress_coalesces_when_loop_is_behind() -> None:
    h = _harness(1)
    h.manager.submit(make_spec(1, task="three"))
    h.step(0)
    slot = h.live_slot(0)
    assert slot.step() == Ok("progress:0.25")
    assert slot.step() == Ok("progress:0.5")
    assert slot.step() == Ok("progress:0.75")
    assert h.loop.pending() == 1  # one drain callback for three events
    h.settle()
    assert slot.pending_coalesced() == 2
    assert [e.progress for e in h.envelopes] == [0.75]
    assert h.manager.metrics().progress_coalesced == 2


# frob:tests python/sadi/jobs/testing.py::FakeSlot.crash
def test_crash_fails_job_and_respawns_slot() -> None:
    h = _harness(1)
    h.manager.submit(make_spec(1, task="three"))
    h.step(0)
    h.live_slot(0).crash(-9)
    h.settle()
    out = h.outcomes[0]
    assert out.state is JobState.FAILED
    assert out.error is not None
    assert out.error.code is JobCode.WORKER_CRASHED
    assert h.manager.metrics().worker_restarts == 1


def test_task_exception_and_unknown_task_fail() -> None:
    h = _harness(1)
    h.manager.submit(make_spec(1, task="boom"))
    h.step(0)
    h.step(0)
    assert h.step(0) == Ok("failed")
    h.manager.submit(make_spec(2, task="nope"))
    assert h.step(0) == Ok("failed:unknown-task")
    assert [o.state for o in h.outcomes] == [JobState.FAILED, JobState.FAILED]
    assert all(o.error and o.error.code is JobCode.TASK_FAILED for o in h.outcomes)


# frob:tests python/sadi/jobs/testing.py::FakeClock.sleep
# frob:tests python/sadi/jobs/testing.py::FakeClock.deadline
# frob:tests python/sadi/jobs/testing.py::FakeClock.monotonic
def test_silent_worker_warns_once_on_fake_time() -> None:
    h = _harness(1)
    h.manager.submit(make_spec(1, task="three"))
    h.step(0)
    h.clock.sleep(5.0)  # advances, never blocks
    assert h.manager.metrics().silent_workers == 0
    h.advance(6.0)
    assert h.manager.metrics().silent_workers == 1
    h.advance(60.0)
    assert h.manager.metrics().silent_workers == 1
    assert h.clock.deadline(1.0) == h.clock.monotonic_ns() + 1_000_000_000


def _scenario(seed: int, pre: int) -> tuple[JobHarness, Interleaver]:
    h = _harness(2)
    h.manager.submit(make_spec(1, task="three", data_version=1, dv=1))
    il = Interleaver(h, seed)
    for _ in range(pre):
        il.tick()
    h.manager.submit(make_spec(2, task="three", data_version=2, dv=2))
    assert isinstance(il.run_until_idle(), Ok)
    return h, il


# frob:tests python/sadi/jobs/testing.py::Interleaver.tick
# frob:tests python/sadi/jobs/testing.py::Interleaver.run_until_idle
@pytest.mark.parametrize("seed", range(60))
def test_supersede_invariants_hold_for_every_seed(seed: int) -> None:
    h, il = _scenario(seed, pre=seed % 7)
    out = {o.job_id.int: o for o in h.outcomes}
    assert out[2].state is JobState.DONE
    assert out[1].state in (JobState.SUPERSEDED, JobState.DONE)
    assert out[1].state is JobState.SUPERSEDED or out[1].discarded or out[1].result is not None
    stale = next(
        (i for i, e in enumerate(h.envelopes) if e.state is ResultState.STALE), -1
    )  # no stale marker => no old envelope was ever published
    assert all(e.data_version == 2 for e in h.envelopes[stale + 1 :])
    assert [e.state for e in h.envelopes].count(ResultState.FINAL) >= 1
    assert h.envelopes[-1].state is ResultState.FINAL
    assert h.envelopes[-1].data_version == 2


# frob:tests python/sadi/jobs/testing.py::Interleaver.replay
def test_recorded_trace_replays_identically() -> None:
    h1, il = _scenario(seed=1234, pre=3)
    h2 = _harness(2)
    h2.manager.submit(make_spec(1, task="three", data_version=1, dv=1))
    pre = il.trace[:3]
    assert isinstance(Interleaver.replay(h2, pre), Ok)
    h2.manager.submit(make_spec(2, task="three", data_version=2, dv=2))
    assert isinstance(Interleaver.replay(h2, il.trace[3:]), Ok)
    assert [(e.key, e.data_version, e.state, e.progress) for e in h1.envelopes] == [
        (e.key, e.data_version, e.state, e.progress) for e in h2.envelopes
    ]
    assert [(o.job_id, o.state) for o in h1.outcomes] == [(o.job_id, o.state) for o in h2.outcomes]


def test_replay_reports_divergence_and_other_seeds_differ() -> None:
    h = _harness(1)
    res = Interleaver.replay(h, ["step:0"])
    assert isinstance(res, Err)
    assert "diverged at 0" in res.error.detail
    traces = {tuple(_scenario(s, pre=2)[1].trace) for s in range(20)}
    assert len(traces) > 1


# frob:ticket 01M6WBZ7QYZPJDF6XR283MEEZ0
# frob:tests python/sadi/jobs/manager.py::JobManager.__init__
def test_harness_injects_clock_without_patching_time() -> None:
    import sadi.jobs.manager as mgr

    real = mgr.time
    h = _harness()
    assert mgr.time is real
    assert h.manager._clock is h.clock  # noqa: SLF001
