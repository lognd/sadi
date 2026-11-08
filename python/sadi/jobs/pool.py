"""Worker processes: `worker_main` (child side), `CancelToken`, and `WorkerSlot` (parent side).

Spawn context only (concurrency.md section 1). Workers never import `sadi.store`; they take
inputs and return results by value. The parent owns one `WorkerSlot` per incarnation of a
worker; a killed or crashed worker is replaced by a new slot object, so late events from the
old one are identifiable by identity.
"""

# frob:ticket 01M6W7R1Z1E430ZNZ51V9NMTHC
from __future__ import annotations

import importlib
import multiprocessing as mp
import os
import queue
import threading
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Protocol, cast
from uuid import UUID

from pydantic import TypeAdapter
from typani import Err, Ok, Result

from sadi.core.errors import JobCode, JobError
from sadi.jobs.state import (
    WORKER_JOIN_S,
    Cancelled,
    Done,
    Failed,
    JobEvent,
    JobSpec,
    Progress,
    Ready,
    Started,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

_CTX = mp.get_context("spawn")
_EVENTS: TypeAdapter[JobEvent] = TypeAdapter(JobEvent)


class Task(Protocol):
    """A job function: `(inputs, token) -> result`; must call `token.check` at cancel points."""

    def __call__(self, inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
        """Run the job and return its result dict."""
        ...


class CancelToken:
    """Cooperative cancel flag that also throttles and emits progress events."""

    def __init__(
        self,
        job_id: UUID,
        flag: threading.Event,
        send: Callable[[dict[str, object]], None],
        interval_ms: int,
    ) -> None:
        self._job_id = job_id
        self._flag = flag
        self._send = send
        self._interval_ns = interval_ms * 1_000_000
        self._last_ns: int | None = None
        self._last_fraction = 0.0

    @property
    def cancelled(self) -> bool:
        """True once a Cancel for this job has arrived (no progress side effect)."""
        return self._flag.is_set()

    def check(self, fraction: float, partial: dict[str, object] | None = None) -> bool:
        """Emit throttled progress; return True if the task must stop now."""
        now = time.monotonic_ns()
        if self._last_ns is None or now - self._last_ns >= self._interval_ns:
            self._last_ns = now
            self._last_fraction = max(self._last_fraction, min(1.0, max(0.0, fraction)))
            event = Progress(
                job_id=self._job_id,
                fraction=self._last_fraction,
                partial=partial,
                mono_ns=now,
            )
            self._send(event.model_dump())
        return self._flag.is_set()


class _WorkerControl:
    """Child-side state shared between the watchdog thread and the task thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: UUID | None = None
        self._flag = threading.Event()
        self._early: set[UUID] = set()

    def begin(self, job_id: UUID) -> threading.Event:
        """Arm a fresh cancel flag for `job_id` (set at once if its Cancel came early)."""
        with self._lock:
            self._flag = threading.Event()
            self._current = job_id
            if job_id in self._early:
                self._early.discard(job_id)
                self._flag.set()
            return self._flag

    def end(self) -> None:
        """Disarm after the job finished."""
        with self._lock:
            self._current = None

    def cancel(self, job_id: UUID) -> None:
        """Record a Cancel from the parent."""
        with self._lock:
            if self._current == job_id:
                self._flag.set()
            else:
                self._early.add(job_id)


def _watchdog(cmd: Connection, control: _WorkerControl, jobs: queue.Queue[JobSpec | None]) -> None:
    """Block on the command pipe; die with the parent (EOF -> os._exit)."""
    while True:
        try:
            msg = cmd.recv()
        except (EOFError, OSError):
            os._exit(0)
        match msg.get("cmd"):
            case "run":
                jobs.put(JobSpec.model_validate(msg["spec"]))
            case "cancel":
                control.cancel(UUID(str(msg["job_id"])))
            case "shutdown":
                jobs.put(None)
                return
            case other:  # pragma: no cover - protocol bug
                _log.error("worker: unknown command %r", other)


def _resolve(task: str) -> Result[Task, JobError]:
    """Import `module:function` inside the worker."""
    module_name, sep, attr = task.partition(":")
    if not sep or not module_name or not attr:
        return Err(JobError(code=JobCode.TASK_FAILED, detail=f"bad task path {task!r}"))
    try:
        fn = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        return Err(JobError(code=JobCode.TASK_FAILED, detail=f"{task}: {exc!r}"))
    return Ok(cast("Task", fn))


def _run_one(
    spec: JobSpec, control: _WorkerControl, send: Callable[[dict[str, object]], None]
) -> None:
    """Execute one job and emit exactly one terminal event."""
    flag = control.begin(spec.job_id)
    try:
        resolved = _resolve(spec.task)
        if isinstance(resolved, Err):
            send(Failed(job_id=spec.job_id, error=resolved.error).model_dump())
            return
        fn = resolved.unwrap()
        send(Started(job_id=spec.job_id).model_dump())
        token = CancelToken(spec.job_id, flag, send, spec.progress_interval_ms)
        t0 = time.perf_counter()
        try:
            result = fn(dict(spec.inputs), token)
        except Exception as exc:  # noqa: BLE001 - task code is untrusted at this boundary
            err = JobError(code=JobCode.TASK_FAILED, detail=f"{spec.task}: {exc!r}")
            send(Failed(job_id=spec.job_id, error=err).model_dump())
            return
        if flag.is_set():
            send(Cancelled(job_id=spec.job_id).model_dump())
        else:
            run_ms = (time.perf_counter() - t0) * 1000.0
            send(Done(job_id=spec.job_id, result=result, run_ms=run_ms).model_dump())
    finally:
        control.end()


def worker_main(slot: int, cmd: Connection, events: Connection) -> None:
    """Entry point of a worker process: announce Ready, then run jobs until Shutdown."""
    control = _WorkerControl()
    jobs: queue.Queue[JobSpec | None] = queue.Queue()
    threading.Thread(
        target=_watchdog, args=(cmd, control, jobs), name="sadi-worker-watchdog", daemon=True
    ).start()

    def send(payload: dict[str, object]) -> None:
        events.send(payload)

    send(Ready(pid=os.getpid(), slot=slot).model_dump())
    while (spec := jobs.get()) is not None:
        _run_one(spec, control, send)


class WorkerSlot:
    """Parent-side handle of one worker incarnation: process, pipes and the pump thread."""

    def __init__(
        self,
        index: int,
        on_event: Callable[[WorkerSlot, JobEvent], None],
        on_death: Callable[[WorkerSlot, int | None, int | None], None],
        post: Callable[[Callable[[], None]], None],
    ) -> None:
        self.index = index
        self._on_event = on_event
        self._on_death = on_death
        self._post = post
        self.ready = False
        self.retired = False
        self.job_id: UUID | None = None
        cmd_recv, self._cmd = _CTX.Pipe(duplex=False)
        self._events, evt_send = _CTX.Pipe(duplex=False)
        self._proc = _CTX.Process(
            target=worker_main,
            args=(index, cmd_recv, evt_send),
            name=f"sadi-worker-{index}",
            daemon=True,
        )
        self._proc.start()
        cmd_recv.close()
        evt_send.close()
        self._lock = threading.Lock()  # leaf lock: guards only the pending-progress cell
        self._pending: Progress | None = None
        self.coalesced = 0
        self._pump = threading.Thread(
            target=self._pump_loop, name=f"sadi-job-pump-{index}", daemon=True
        )
        self._pump.start()
        _log.info("slot %d: spawned worker pid=%s", index, self._proc.pid)

    @property
    def pid(self) -> int | None:
        """OS pid of the worker."""
        return self._proc.pid

    def send_run(self, spec: JobSpec) -> Result[None, JobError]:
        """Send a job to an idle, ready worker."""
        if self.job_id is not None:
            return Err(JobError(code=JobCode.SLOT_BUSY, detail=f"slot {self.index}"))
        try:
            self._cmd.send({"cmd": "run", "spec": spec.model_dump(mode="json")})
        except (OSError, ValueError) as exc:
            return Err(JobError(code=JobCode.WORKER_CRASHED, detail=f"slot {self.index}: {exc!r}"))
        self.job_id = spec.job_id
        return Ok(None)

    def send_cancel(self, job_id: UUID) -> None:
        """Ask the worker to cancel `job_id`; a dead pipe is ignored (death is reported by pump)."""
        try:
            self._cmd.send({"cmd": "cancel", "job_id": str(job_id)})
        except (OSError, ValueError):
            _log.warning("slot %d: cancel for %s not delivered (pipe closed)", self.index, job_id)

    def kill(self) -> None:
        """Hard-kill the worker and retire this slot object."""
        self.retired = True
        _log.warning("slot %d: killing worker pid=%s", self.index, self._proc.pid)
        self._proc.kill()
        self._close_cmd()

    def request_shutdown(self) -> None:
        """Politely ask the worker to exit."""
        self.retired = True
        try:
            self._cmd.send({"cmd": "shutdown"})
        except (OSError, ValueError):
            _log.debug("slot %d: shutdown not delivered (already gone)", self.index)

    def join(self, timeout_s: float = WORKER_JOIN_S) -> bool:
        """Join the process (kill it on timeout) and the pump thread; True if it exited politely."""
        self._proc.join(timeout_s)
        polite = not self._proc.is_alive()
        if not polite:
            _log.warning("slot %d: worker did not exit in %.1fs, killing", self.index, timeout_s)
            self._proc.kill()
            self._proc.join(timeout_s)
        self._close_cmd()
        self._pump.join(timeout_s)
        return polite

    def pending_coalesced(self) -> int:
        """Number of Progress events dropped in favour of a newer one."""
        with self._lock:
            return self.coalesced

    def take_progress(self) -> Progress | None:
        """Loop side: take the newest pending Progress (if any)."""
        with self._lock:
            event, self._pending = self._pending, None
            return event

    def _close_cmd(self) -> None:
        try:
            self._cmd.close()
        except OSError:  # pragma: no cover - already closed
            pass

    def _pump_loop(self) -> None:
        """Pump thread: block on the event pipe, coalesce Progress, post to the loop."""
        while True:
            try:
                raw = self._events.recv()
            except (EOFError, OSError):
                break
            try:
                event = _EVENTS.validate_python(raw)
            except ValueError:
                _log.exception("slot %d: malformed event %r", self.index, raw)
                continue
            if not self._deliver(event):
                return
        self._proc.join(WORKER_JOIN_S)
        pid, code = self._proc.pid, self._proc.exitcode
        self._events.close()
        self._safe_post(lambda: self._on_death(self, pid, code))

    def _deliver(self, event: JobEvent) -> bool:
        if isinstance(event, Progress):
            with self._lock:
                replaced = self._pending is not None
                self._pending = event
                if replaced:
                    self.coalesced += 1
            if replaced:
                return True
            return self._safe_post(lambda: self._drain())
        return self._safe_post(lambda: self._on_event(self, event))

    def _drain(self) -> None:
        event = self.take_progress()
        if event is not None:
            self._on_event(self, event)

    def _safe_post(self, fn: Callable[[], None]) -> bool:
        try:
            self._post(fn)
        except RuntimeError:
            _log.debug("slot %d: loop closed, pump exits", self.index)
            return False
        return True
