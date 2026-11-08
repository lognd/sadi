"""Direct tests of one `WorkerSlot`: run, cancel, kill and join against a real spawn worker."""

# frob:ticket 01M6XAY79MWPV07858YAKSBJQ6
from __future__ import annotations

import queue
import time
from pathlib import Path
from uuid import uuid4

from sadi.core.errors import JobCode
from sadi.jobs import JobKey, JobSpec
from sadi.jobs.pool import CancelToken, WorkerSlot
from sadi.jobs.state import Cancelled, Done, JobEvent, Ready

TIMEOUT = 60.0


def t_echo(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Return the input unchanged."""
    return {"x": inputs["x"]}


def t_coop(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Spin until the cancel token fires."""
    Path(str(inputs["started"])).touch()
    while not token.cancelled:
        time.sleep(0.002)
    return {}


def _spec(fn: str, **inputs: object) -> JobSpec:
    return JobSpec(
        job_id=uuid4(),
        key=JobKey("k"),
        data_version=1,
        task=f"{__name__}:{fn}",
        inputs=dict(inputs),
        progress_interval_ms=0,
    )


class _Rig:
    """A slot whose events and death notices land on thread-safe queues."""

    def __init__(self) -> None:
        self.events: queue.Queue[JobEvent] = queue.Queue()
        self.deaths: queue.Queue[tuple[int | None, int | None]] = queue.Queue()
        self.slot = WorkerSlot(
            0,
            lambda _s, ev: self.events.put(ev),
            lambda _s, pid, code: self.deaths.put((pid, code)),
            lambda fn: fn(),
        )

    def next(self) -> JobEvent:
        """Block for the next event."""
        return self.events.get(timeout=TIMEOUT)

    def until(self, kind: type) -> JobEvent:
        """Drain events until one of `kind` arrives."""
        while True:
            ev = self.next()
            if isinstance(ev, kind):
                return ev


# frob:tests python/sadi/jobs/pool.py::WorkerSlot.send_run
# frob:tests python/sadi/jobs/pool.py::WorkerSlot.join
def test_send_run_executes_and_busy_slot_refuses_then_join_is_polite() -> None:
    rig = _Rig()
    try:
        rig.until(Ready)
        spec = _spec("t_echo", x=7)
        assert rig.slot.send_run(spec).is_ok
        assert rig.slot.job_id == spec.job_id
        busy = rig.slot.send_run(_spec("t_echo", x=8))
        assert busy.is_err and busy.danger_err.code is JobCode.SLOT_BUSY
        done = rig.until(Done)
        assert isinstance(done, Done) and done.job_id == spec.job_id
        rig.slot.request_shutdown()
        # wait for the pump's death notice first: join() racing the pump's own proc.join()
        # can lose the waitpid and misreport a polite exit (filed as a separate bug)
        _pid, code = rig.deaths.get(timeout=TIMEOUT)
        assert code == 0
        assert rig.slot.join() is True
    finally:
        rig.slot.kill()


# frob:tests python/sadi/jobs/pool.py::WorkerSlot.send_cancel
def test_send_cancel_stops_a_cooperative_job(tmp_path: Path) -> None:
    rig = _Rig()
    try:
        rig.until(Ready)
        started = tmp_path / "started"
        spec = _spec("t_coop", started=str(started))
        assert rig.slot.send_run(spec).is_ok
        while not started.exists():
            time.sleep(0.005)
        rig.slot.send_cancel(spec.job_id)
        assert isinstance(rig.until(Cancelled), Cancelled)
    finally:
        rig.slot.kill()


# frob:tests python/sadi/jobs/pool.py::WorkerSlot.kill
# frob:tests python/sadi/jobs/pool.py::WorkerSlot.join
def test_kill_retires_slot_reports_death_and_send_run_errors() -> None:
    rig = _Rig()
    rig.until(Ready)
    rig.slot.kill()
    assert rig.slot.retired
    pid, code = rig.deaths.get(timeout=TIMEOUT)
    assert pid == rig.slot.pid and code is not None and code != 0
    res = rig.slot.send_run(_spec("t_echo", x=1))
    assert res.is_err and res.danger_err.code is JobCode.WORKER_CRASHED
    rig.slot.send_cancel(uuid4())  # dead pipe: ignored, must not raise
    assert rig.slot.join(5.0) is True
