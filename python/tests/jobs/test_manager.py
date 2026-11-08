"""Deterministic tests for the job system: gates are files and events, never timing guesses."""

# frob:ticket 01M6W7R1Z1E430ZNZ51V9NMTHC
from __future__ import annotations

import asyncio
import os
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from sadi.core.errors import JobCode
from sadi.jobs import (
    JobKey,
    JobManager,
    JobOutcome,
    JobSpec,
    JobState,
    ResultEnvelope,
    ResultState,
)
from sadi.jobs.pool import CancelToken
from sadi.jobs.state import JobId, Outcome, Priority

T = TypeVar("T")
TIMEOUT = 60.0


# ---- task functions (run inside spawn workers; referenced by import path) -----------------


def _wait_file(path: str, token: CancelToken | None = None) -> bool:
    """Poll for a gate file; True if it appeared, False if cancelled first."""
    while not Path(path).exists():
        if token is not None and token.cancelled:
            return False
        time.sleep(0.002)
    return True


def t_quick(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Return the input."""
    return {"x": inputs["x"], "store_loaded": "sadi.store" in sys.modules}


def t_progress(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Emit one partial then finish."""
    token.check(0.5, {"p": 1})
    return {"done": True}


def t_gate(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Block until the release file exists; honour no cancel (finishes if released)."""
    Path(str(inputs["started"])).touch()
    _wait_file(str(inputs["release"]))
    return {"tag": inputs.get("tag")}


def t_coop(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Spin until the cancel token fires."""
    Path(str(inputs["started"])).touch()
    while not token.cancelled:
        time.sleep(0.002)
    return {}


def t_stubborn(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Ignore cancellation forever (forces the hard kill)."""
    Path(str(inputs["started"])).touch()
    while True:
        time.sleep(0.01)


def t_crash(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Kill the worker process outright."""
    os._exit(3)


def t_boom(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Raise an ordinary exception."""
    raise ValueError("boom")


# ---- helpers ----------------------------------------------------------------------------


def _spec(
    fn: str,
    key: str = "k",
    dv: int = 1,
    priority: Priority = "background",
    **inputs: object,
) -> JobSpec:
    return JobSpec(
        job_id=uuid4(),
        key=JobKey(key),
        data_version=dv,
        task=f"{__name__}:{fn}",
        inputs=dict(inputs),
        priority=priority,
        progress_interval_ms=0,
    )


def _run(body: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(asyncio.wait_for(body(), TIMEOUT))


async def _wait_file_async(path: Path) -> None:
    while not path.exists():
        await asyncio.sleep(0.005)


def _submit(mgr: JobManager, spec: JobSpec) -> JobId:
    return mgr.submit(spec).unwrap()


async def _outcome(mgr: JobManager, job_id: JobId) -> JobOutcome:
    out = await mgr.wait(job_id)
    assert out is not None
    return out


# ---- tests ------------------------------------------------------------------------------


# frob:tests python/sadi/jobs/state.py::JobState.next_states
# frob:tests python/sadi/jobs/state.py::JobState.can_go
def test_state_table_is_total_and_terminals_are_sinks() -> None:
    for state in JobState:
        nxt = state.next_states
        if state.is_terminal:
            assert nxt == frozenset()
        else:
            assert nxt
        for to in nxt:
            assert state.can_go(to)
    assert not JobState.DONE.can_go(JobState.RUNNING)


# frob:tests python/sadi/jobs/manager.py::JobManager.submit
# frob:tests python/sadi/jobs/manager.py::JobManager.wait
# frob:tests python/sadi/jobs/pool.py::worker_main
# frob:tests python/sadi/jobs/pool.py::Task.__call__
# frob:tests python/sadi/jobs/pool.py::WorkerSlot.pid
# frob:tests python/sadi/jobs/pool.py::WorkerSlot.__init__
# frob:tests python/sadi/jobs/manager.py::JobManager.start
# frob:tests python/sadi/jobs/manager.py::JobManager.__init__
def test_done_result_and_worker_never_imports_store() -> None:
    async def body() -> None:
        mgr = JobManager(1)
        mgr.start()
        try:
            out = await _outcome(mgr, _submit(mgr, _spec("t_quick", x=7)))
            assert out.state is JobState.DONE
            assert out.result == {"x": 7, "store_loaded": False}
            env = mgr.latest()[JobKey("k")]
            assert env.state is ResultState.FINAL
            assert env.result_version == 1
        finally:
            await mgr.shutdown()

    _run(body)


# frob:tests python/sadi/jobs/manager.py::JobManager.submit
# frob:tests python/sadi/jobs/pool.py::WorkerSlot.take_progress
def test_progress_streams_as_refining_then_final() -> None:
    async def body() -> None:
        seen: list[ResultEnvelope] = []
        mgr = JobManager(1, sink=seen.append)
        mgr.start()
        try:
            out = await _outcome(mgr, _submit(mgr, _spec("t_progress")))
            assert out.state is JobState.DONE
            assert [e.state for e in seen] == [ResultState.REFINING, ResultState.FINAL]
            assert [e.result_version for e in seen] == [1, 2]
            assert mgr.metrics().done_total == 1
        finally:
            await mgr.shutdown()

    _run(body)


# frob:tests python/sadi/jobs/manager.py::JobManager.cancel
def test_cooperative_cancel_needs_no_kill(tmp_path: Path) -> None:
    async def body() -> None:
        started = tmp_path / "s"
        mgr = JobManager(1)
        mgr.start()
        try:
            jid = _submit(mgr, _spec("t_coop", started=str(started)))
            await _wait_file_async(started)
            assert mgr.cancel(jid).is_ok
            out = await _outcome(mgr, jid)
            assert out.state is JobState.CANCELLED
            assert not out.killed
            assert mgr.cancel(jid).is_err  # already terminal
        finally:
            await mgr.shutdown()

    _run(body)


# frob:tests python/sadi/jobs/manager.py::JobManager._kill
def test_hard_kill_after_grace_and_slot_is_respawned(tmp_path: Path) -> None:
    async def body() -> None:
        started = tmp_path / "s"
        mgr = JobManager(1, grace_s=0.2)
        mgr.start()
        try:
            jid = _submit(mgr, _spec("t_stubborn", started=str(started)))
            await _wait_file_async(started)
            mgr.cancel(jid).unwrap()
            out = await _outcome(mgr, jid)
            assert out.state is JobState.CANCELLED
            assert out.killed
            nxt = await _outcome(mgr, _submit(mgr, _spec("t_quick", key="k2", x=1)))
            assert nxt.state is JobState.DONE
            m = mgr.metrics()
            assert m.killed_total == 1
            assert m.worker_restarts == 1
        finally:
            await mgr.shutdown()

    _run(body)


# frob:tests python/sadi/jobs/manager.py::JobManager.submit
def test_supersede_queued_job_never_runs(tmp_path: Path) -> None:
    async def body() -> None:
        started, release = tmp_path / "s", tmp_path / "r"
        mgr = JobManager(1)
        mgr.start()
        try:
            blocker = _submit(
                mgr, _spec("t_gate", key="b", started=str(started), release=str(release))
            )
            await _wait_file_async(started)
            old = _submit(mgr, _spec("t_quick", key="k", dv=1, x=1))
            new = _submit(mgr, _spec("t_quick", key="k", dv=2, x=2))
            assert mgr.state_of(old) is JobState.SUPERSEDED
            release.touch()
            assert (await _outcome(mgr, blocker)).state is JobState.DONE
            out = await _outcome(mgr, new)
            assert out.result is not None and out.result["x"] == 2
            assert (await _outcome(mgr, old)).state is JobState.SUPERSEDED
            assert mgr.latest()[JobKey("k")].data_version == 2
            assert mgr.metrics().superseded_total == 1
        finally:
            await mgr.shutdown()

    _run(body)


# frob:tests python/sadi/jobs/manager.py::JobManager.submit
def test_supersede_running_job_discards_old_result(tmp_path: Path) -> None:
    async def body() -> None:
        started, release = tmp_path / "s", tmp_path / "r"
        mgr = JobManager(1)
        mgr.start()
        try:
            old = _submit(
                mgr, _spec("t_gate", dv=1, tag="old", started=str(started), release=str(release))
            )
            await _wait_file_async(started)
            new = _submit(mgr, _spec("t_quick", dv=2, x=2))
            release.touch()
            old_out = await _outcome(mgr, old)
            assert old_out.state is JobState.SUPERSEDED
            assert old_out.result is None
            new_out = await _outcome(mgr, new)
            assert new_out.state is JobState.DONE
            env = mgr.latest()[JobKey("k")]
            assert env.job_id == new and env.state is ResultState.FINAL
        finally:
            await mgr.shutdown()

    _run(body)


# frob:tests python/sadi/jobs/manager.py::JobManager._on_death
def test_worker_crash_fails_job_with_typed_error_and_server_survives() -> None:
    async def body() -> None:
        mgr = JobManager(1)
        mgr.start()
        try:
            out = await _outcome(mgr, _submit(mgr, _spec("t_crash")))
            assert out.state is JobState.FAILED
            assert out.error is not None and out.error.code is JobCode.WORKER_CRASHED
            after = await _outcome(mgr, _submit(mgr, _spec("t_quick", key="k2", x=3)))
            assert after.state is JobState.DONE
            assert mgr.metrics().worker_restarts == 1
        finally:
            await mgr.shutdown()

    _run(body)


# frob:tests python/sadi/jobs/pool.py::_run_one
def test_task_exception_and_bad_task_path_are_typed_failures() -> None:
    async def body() -> None:
        mgr = JobManager(1)
        mgr.start()
        try:
            boom = await _outcome(mgr, _submit(mgr, _spec("t_boom")))
            assert boom.state is JobState.FAILED
            assert boom.error is not None and boom.error.code is JobCode.TASK_FAILED
            bad = JobSpec(job_id=uuid4(), key=JobKey("k"), data_version=2, task="nope:missing")
            out = await _outcome(mgr, _submit(mgr, bad))
            assert out.state is JobState.FAILED and out.error is not None
            assert mgr.metrics().failed_total == 2
        finally:
            await mgr.shutdown()

    _run(body)


# frob:tests python/sadi/jobs/manager.py::JobManager._dispatch
def test_interactive_slot_is_reserved_from_background(tmp_path: Path) -> None:
    async def body() -> None:
        started, release = tmp_path / "s", tmp_path / "r"
        mgr = JobManager(2)
        mgr.start()
        try:
            a = _submit(mgr, _spec("t_gate", key="a", started=str(started), release=str(release)))
            await _wait_file_async(started)
            b = _submit(mgr, _spec("t_quick", key="b", x=1))  # background: slot 0 is reserved
            c = _submit(mgr, _spec("t_quick", key="c", priority="interactive", x=2))
            assert (await _outcome(mgr, c)).state is JobState.DONE
            assert mgr.state_of(b) is JobState.QUEUED
            release.touch()
            assert (await _outcome(mgr, a)).state is JobState.DONE
            assert (await _outcome(mgr, b)).state is JobState.DONE
        finally:
            await mgr.shutdown()

    _run(body)


# frob:tests python/sadi/jobs/manager.py::JobManager.shutdown
# frob:tests python/sadi/jobs/pool.py::WorkerSlot.request_shutdown
def test_shutdown_cancels_running_kills_stubborn_and_rejects_new(tmp_path: Path) -> None:
    async def body() -> None:
        started = tmp_path / "s"
        mgr = JobManager(1, grace_s=0.2)
        mgr.start()
        jid = _submit(mgr, _spec("t_stubborn", started=str(started)))
        await _wait_file_async(started)
        queued = _submit(mgr, _spec("t_quick", key="q", x=1))
        res = await mgr.shutdown(grace_s=0.2)
        assert res.is_ok
        out = await _outcome(mgr, jid)
        assert out.state is JobState.CANCELLED and out.killed
        assert (await _outcome(mgr, queued)).state is JobState.CANCELLED
        late = mgr.submit(_spec("t_quick", x=1))
        assert late.is_err and late.unwrap_err().code is JobCode.SHUTTING_DOWN

    _run(body)


# frob:tests python/sadi/jobs/manager.py::JobManager.cancel_key
# frob:tests python/sadi/jobs/manager.py::JobManager.wait_for_state
def test_cancel_key_and_wait_for_state(tmp_path: Path) -> None:
    async def body() -> None:
        started = tmp_path / "s"
        mgr = JobManager(1)
        mgr.start()
        try:
            jid = _submit(mgr, _spec("t_coop", started=str(started)))
            await mgr.wait_for_state(jid, JobState.RUNNING)
            await _wait_file_async(started)
            assert mgr.cancel_key(JobKey("k")).is_ok
            assert (await _outcome(mgr, jid)).state is JobState.CANCELLED
            assert mgr.cancel_key(JobKey("k")).is_err
            assert mgr.cancel_key(JobKey("never")).is_err
        finally:
            await mgr.shutdown()

    _run(body)


# frob:tests python/sadi/jobs/pool.py::CancelToken.check
# frob:tests python/sadi/jobs/pool.py::CancelToken.cancelled
# frob:tests python/sadi/jobs/pool.py::CancelToken.__init__
def test_cancel_token_throttles_and_keeps_fraction_monotonic() -> None:
    import threading

    sent: list[dict[str, object]] = []
    flag = threading.Event()
    token = CancelToken(uuid4(), flag, sent.append, 60_000)
    assert not token.check(0.4)
    assert not token.check(0.2)  # throttled: no second event inside the interval
    assert len(sent) == 1 and sent[0]["fraction"] == 0.4
    flag.set()
    assert token.cancelled and token.check(0.9)


# frob:tests python/sadi/jobs/state.py::JobState.is_terminal
# frob:tests python/sadi/jobs/state.py::Outcome.terminal_state
# frob:tests python/sadi/jobs/state.py::default_worker_count
def test_terminal_flags_outcome_mapping_and_worker_default() -> None:
    from sadi.jobs.state import default_worker_count

    assert {s for s in JobState if s.is_terminal} == {
        JobState.DONE,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.SUPERSEDED,
    }
    assert Outcome.CANCELLED.terminal_state is JobState.CANCELLED
    assert Outcome.SUPERSEDED.terminal_state is JobState.SUPERSEDED
    assert Outcome.NONE.terminal_state is JobState.DONE
    assert default_worker_count() >= 1


# frob:tests python/sadi/jobs/manager.py::JobManager
def test_jobs_package_has_no_web_or_store_imports() -> None:
    import subprocess

    code = (
        "import sys, sadi.jobs; "
        "bad = [m for m in sys.modules if m.startswith(('sadi.store', 'sadi.web'))]; "
        "sys.exit(1 if bad else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
