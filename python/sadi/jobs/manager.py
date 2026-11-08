"""JobManager: latest-wins job scheduling over a spawn-context worker pool.

Owned by the asyncio loop thread (concurrency.md section 2): all state is single-threaded and
lock-free; pump threads only post callbacks via `loop.call_soon_threadsafe`. Implements
sections 6, 7, 8, 9.3 (stale/refining/final envelopes) and 11 step 4 of docs/concurrency.md.
"""

# frob:ticket 01M6W7R1Z1E430ZNZ51V9NMTHC
# frob:ticket 01M6WBZ7QYZPJDF6XR283MEEZ0
from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar, cast
from uuid import UUID

from typani import Err, Ok, Result

from sadi.core.errors import JobCode, JobError
from sadi.jobs.pool import WorkerSlot
from sadi.jobs.state import (
    CANCEL_GRACE_S,
    WORKER_HEARTBEAT_S,
    WORKER_JOIN_S,
    Cancelled,
    Done,
    Failed,
    JobEvent,
    JobId,
    JobKey,
    JobMetrics,
    JobOutcome,
    JobSpec,
    JobState,
    Outcome,
    Progress,
    Ready,
    ResultEnvelope,
    ResultState,
    Started,
    default_worker_count,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)
_T = TypeVar("_T")

_HISTORY = 256


class Clock(Protocol):
    """Time source seam: monotonic seconds for durations, wall nanoseconds for stamps."""

    def monotonic(self) -> float:
        """Monotonic seconds."""
        ...

    def time_ns(self) -> int:
        """Wall-clock nanoseconds."""
        ...


#: Builds a worker slot: `(index, on_event, on_death, post) -> WorkerSlot`.
SlotFactory = Callable[
    [int, Callable[..., None], Callable[..., None], Callable[[Callable[[], None]], None]],
    WorkerSlot,
]


@dataclass
class _Job:
    """Mutable manager-private record of one job."""

    spec: JobSpec
    state: JobState = JobState.QUEUED
    outcome: Outcome = Outcome.NONE
    slot: WorkerSlot | None = None
    killed: bool = False
    entered: float = 0.0
    last_event: float = 0.0
    last_fraction: float = 0.0
    warned_silent: bool = False
    grace: asyncio.TimerHandle | None = None
    silence: asyncio.TimerHandle | None = None
    done: asyncio.Future[JobOutcome] | None = None


class JobManager:
    """Submit, cancel and supersede CPU jobs on a process pool; loop-thread only."""

    def __init__(
        self,
        workers: int | None = None,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        grace_s: float = CANCEL_GRACE_S,
        heartbeat_s: float = WORKER_HEARTBEAT_S,
        sink: Callable[[ResultEnvelope], None] | None = None,
        on_outcome: Callable[[JobOutcome], None] | None = None,
        clock: Clock = time,
        spawn: SlotFactory = WorkerSlot,
    ) -> None:
        self._clock = clock
        self._spawn_slot = spawn
        self._loop = loop or asyncio.get_running_loop()
        self._thread = threading.current_thread()
        self._n = workers if workers is not None else default_worker_count()
        self._grace_s = grace_s
        self._heartbeat_s = heartbeat_s
        self._sink = sink
        self._on_outcome = on_outcome
        self._slots: list[WorkerSlot] = []
        self._jobs: dict[UUID, _Job] = {}
        self._history: OrderedDict[UUID, JobOutcome] = OrderedDict()
        self._queues: dict[str, deque[_Job]] = {"interactive": deque(), "background": deque()}
        self._current: dict[JobKey, UUID] = {}
        self._key_version: dict[JobKey, int] = {}
        self._latest: dict[JobKey, ResultEnvelope] = {}
        self._result_version: dict[JobKey, int] = {}
        self._state_waiters: list[tuple[UUID, JobState, asyncio.Future[None]]] = []
        self._shutting_down = False
        self._started = False
        self._counts: dict[str, int] = dict.fromkeys(
            (
                "submitted",
                "done",
                "failed",
                "cancelled",
                "superseded",
                "killed",
                "restarts",
                "late",
                "silent",
                "discarded",
                "coalesced",
            ),
            0,
        )

    # ---- public API -------------------------------------------------------------------

    def start(self) -> None:
        """Spawn the worker slots (they report Ready asynchronously)."""
        self._assert_loop()
        if self._started:
            return
        self._started = True
        _log.info("job manager: starting %d workers", self._n)
        self._slots = [self._spawn(i) for i in range(self._n)]

    def submit(self, spec: JobSpec) -> Result[JobId, JobError]:
        """Queue `spec`; a live job with the same key is superseded (latest wins)."""
        self._assert_loop()
        if self._shutting_down:
            _log.warning("submit %s rejected: shutting down", spec.job_id)
            return Err(JobError(code=JobCode.SHUTTING_DOWN))
        assert spec.job_id not in self._jobs, "duplicate job_id is a programmer bug"
        job = _Job(spec, entered=self._clock.monotonic(), last_event=self._clock.monotonic())
        self._jobs[spec.job_id] = job
        self._counts["submitted"] += 1
        _log.info(
            "job %s key=%s dv=%d: submitted task=%s prio=%s",
            spec.job_id, spec.key, spec.data_version, spec.task, spec.priority,
        )  # fmt: skip
        prev = self._current.get(spec.key)
        old = self._jobs.get(prev) if prev is not None else None
        self._current[spec.key] = spec.job_id
        self._key_version[spec.key] = max(self._key_version.get(spec.key, 0), spec.data_version)
        if old is not None and not old.state.is_terminal:
            self._stop(old, Outcome.SUPERSEDED)
        self._mark_stale(spec.key, spec.data_version)
        self._queues[spec.priority].append(job)
        self._dispatch()
        return Ok(JobId(spec.job_id))

    def cancel(self, job_id: JobId) -> Result[None, JobError]:
        """Cancel a live job (cooperative, then kill after the grace)."""
        self._assert_loop()
        job = self._jobs.get(job_id)
        if job is None or job.state.is_terminal:
            return Err(JobError(code=JobCode.UNKNOWN, detail=str(job_id)))
        self._stop(job, Outcome.CANCELLED)
        return Ok(None)

    def cancel_key(self, key: JobKey) -> Result[None, JobError]:
        """Cancel the live job of `key` without submitting a replacement."""
        self._assert_loop()
        job = self._jobs.get(self._current.get(key, UUID(int=0)))
        if job is None or job.state.is_terminal:
            return Err(JobError(code=JobCode.UNKNOWN, detail=str(key)))
        self._stop(job, Outcome.CANCELLED)
        return Ok(None)

    async def shutdown(self, grace_s: float | None = None) -> Result[None, JobError]:
        """Cancel everything, wait one shared grace, kill survivors, stop and join workers."""
        self._assert_loop()
        grace = self._grace_s if grace_s is None else grace_s
        self._shutting_down = True
        live = [j for j in self._jobs.values() if not j.state.is_terminal]
        _log.info("job manager: shutdown, %d live jobs, grace=%.2fs", len(live), grace)
        futures = [self._future(j) for j in live]
        for job in live:
            self._stop(job, Outcome.CANCELLED, with_grace=False)
        if futures:
            await asyncio.wait(futures, timeout=grace)
        for job in live:
            if not job.state.is_terminal:
                self._kill(job)
        slots, self._slots = self._slots, []
        for slot in slots:
            slot.request_shutdown()
        await asyncio.gather(
            *(self._loop.run_in_executor(None, s.join, WORKER_JOIN_S) for s in slots)
        )
        for slot in slots:
            self._counts["coalesced"] += slot.pending_coalesced()
        _log.info("job manager: shutdown complete")
        return Ok(None)

    def metrics(self) -> JobMetrics:
        """Return an immutable counters snapshot."""
        c = self._counts
        coalesced = c["coalesced"] + sum(s.pending_coalesced() for s in self._slots)
        running = sum(
            1 for j in self._jobs.values() if j.state in (JobState.RUNNING, JobState.PROGRESSING)
        )
        return JobMetrics(
            submitted_total=c["submitted"],
            done_total=c["done"],
            failed_total=c["failed"],
            cancelled_total=c["cancelled"],
            superseded_total=c["superseded"],
            killed_total=c["killed"],
            worker_restarts=c["restarts"],
            late_events=c["late"],
            progress_coalesced=coalesced,
            silent_workers=c["silent"],
            discarded_results=c["discarded"],
            queued=sum(len(q) for q in self._queues.values()),
            running=running,
        )

    def state_of(self, job_id: JobId) -> JobState | None:
        """Current or final state of a job, or None if unknown/evicted."""
        job = self._jobs.get(job_id)
        if job is not None:
            return job.state
        done = self._history.get(job_id)
        return done.state if done is not None else None

    def latest(self) -> dict[JobKey, ResultEnvelope]:
        """Latest emitted envelope per key."""
        return dict(self._latest)

    async def wait(self, job_id: JobId) -> JobOutcome | None:
        """Await a job's terminal outcome (None if the id is unknown)."""
        self._assert_loop()
        if (done := self._history.get(job_id)) is not None:
            return done
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return await self._future(job)

    async def wait_for_state(self, job_id: JobId, state: JobState) -> None:
        """Return once the job has been in `state` (or is terminal)."""
        self._assert_loop()
        job = self._jobs.get(job_id)
        if job is None or job.state == state or job.state.is_terminal:
            return
        fut = cast("asyncio.Future[None]", self._loop.create_future())
        self._state_waiters.append((job_id, state, fut))
        await fut

    # ---- internals: lifecycle ---------------------------------------------------------

    def _assert_loop(self) -> None:
        assert threading.current_thread() is self._thread, "JobManager is loop-thread only"

    def _post(self, fn: Callable[[], None]) -> None:
        self._loop.call_soon_threadsafe(fn)

    def _spawn(self, index: int) -> WorkerSlot:
        return self._spawn_slot(index, self._on_event, self._on_death, self._post)

    def _future(self, job: _Job) -> asyncio.Future[JobOutcome]:
        if job.done is None:
            job.done = cast("asyncio.Future[JobOutcome]", self._loop.create_future())
        return job.done

    def _transition(self, job: _Job, to: JobState, why: str = "") -> None:
        frm = job.state
        assert frm.can_go(to), f"illegal transition {frm} -> {to}"
        now = self._clock.monotonic()
        level = _log.error if to is JobState.FAILED else _log.info
        level(
            "job %s key=%s dv=%d: %s -> %s after %.0f ms %s",
            job.spec.job_id, job.spec.key, job.spec.data_version, frm, to,
            (now - job.entered) * 1000.0, why,
        )  # fmt: skip
        job.state = to
        job.entered = now
        for waiter in [w for w in self._state_waiters if w[0] == job.spec.job_id]:
            if waiter[1] == to or to.is_terminal:
                self._state_waiters.remove(waiter)
                if not waiter[2].done():
                    waiter[2].set_result(None)

    def _finish(
        self,
        job: _Job,
        to: JobState,
        *,
        error: JobError | None = None,
        result: dict[str, object] | None = None,
        why: str = "",
    ) -> None:
        """Move `job` to a terminal state, free its slot and report the outcome."""
        self._transition(job, to, why)
        for handle in (job.grace, job.silence):
            if handle is not None:
                handle.cancel()
        job.grace = job.silence = None
        slot = job.slot
        if slot is not None and slot.job_id == job.spec.job_id:
            slot.job_id = None
        key = {
            JobState.DONE: "done",
            JobState.FAILED: "failed",
            JobState.CANCELLED: "cancelled",
            JobState.SUPERSEDED: "superseded",
        }[to]
        self._counts[key] += 1
        current = self._current.get(job.spec.key) == job.spec.job_id
        outcome = JobOutcome(
            job_id=job.spec.job_id,
            key=job.spec.key,
            data_version=job.spec.data_version,
            state=to,
            killed=job.killed,
            discarded=to is JobState.DONE and not current,
            error=error,
            result=result,
        )
        del self._jobs[job.spec.job_id]
        self._history[job.spec.job_id] = outcome
        while len(self._history) > _HISTORY:
            self._history.popitem(last=False)
        if job.done is not None and not job.done.done():
            job.done.set_result(outcome)
        if self._on_outcome is not None:
            self._call(self._on_outcome, outcome)
        self._dispatch()

    def _stop(self, job: _Job, outcome: Outcome, *, with_grace: bool = True) -> None:
        """Cancel/supersede: remove if queued, else cooperative cancel plus grace timer."""
        if job.state is JobState.QUEUED:
            self._queues[job.spec.priority].remove(job)
            self._finish(job, outcome.terminal_state, why="(queued, never sent)")
            return
        if job.outcome is not Outcome.NONE:
            _log.debug("job %s: already stopping (%s)", job.spec.job_id, job.outcome)
            return
        job.outcome = outcome
        assert job.slot is not None
        _log.info(
            "job %s: sending Cancel (%s), grace %.2fs", job.spec.job_id, outcome, self._grace_s
        )
        job.slot.send_cancel(job.spec.job_id)
        if with_grace:
            job.grace = self._loop.call_later(self._grace_s, self._grace_expired, job)

    def _grace_expired(self, job: _Job) -> None:
        job.grace = None
        if not job.state.is_terminal:
            self._kill(job)

    def _kill(self, job: _Job) -> None:
        """Hard-kill the job's worker, finish the job as killed and respawn the slot."""
        slot = job.slot
        assert slot is not None
        job.killed = True
        self._counts["killed"] += 1
        slot.kill()
        outcome = job.outcome if job.outcome is not Outcome.NONE else Outcome.CANCELLED
        self._finish(job, outcome.terminal_state, why="(killed after grace)")
        self._replace(slot)

    def _replace(self, slot: WorkerSlot) -> None:
        """Respawn a retired or dead slot unless the manager is shutting down."""
        if self._shutting_down or slot not in self._slots:
            return
        self._counts["coalesced"] += slot.pending_coalesced()
        self._counts["restarts"] += 1
        self._slots[self._slots.index(slot)] = self._spawn(slot.index)

    # ---- internals: dispatch ----------------------------------------------------------

    def _dispatch(self) -> None:
        """Hand queued jobs to idle ready slots: interactive first; slot 0 is reserved."""
        for slot in self._slots:
            if not slot.ready or slot.job_id is not None or slot.retired:
                continue
            reserved = self._n > 1 and slot.index == 0
            job = self._next_job(interactive_only=reserved)
            if job is None:
                continue
            match slot.send_run(job.spec):
                case Err(error):
                    _log.error("slot %d: send failed: %s; requeue", slot.index, error.detail)
                    slot.ready = False
                    self._queues[job.spec.priority].appendleft(job)
                case Ok():
                    job.slot = slot
                    job.last_event = self._clock.monotonic()
                    self._transition(job, JobState.RUNNING, f"on slot {slot.index}")
                    job.silence = self._loop.call_later(self._heartbeat_s, self._check_silent, job)

    def _next_job(self, *, interactive_only: bool) -> _Job | None:
        for prio in ("interactive",) if interactive_only else ("interactive", "background"):
            if self._queues[prio]:
                return self._queues[prio].popleft()
        return None

    def _check_silent(self, job: _Job) -> None:
        job.silence = None
        if job.state.is_terminal:
            return
        quiet = self._clock.monotonic() - job.last_event
        if quiet >= self._heartbeat_s and not job.warned_silent:
            job.warned_silent = True
            self._counts["silent"] += 1
            _log.warning("job %s: worker silent for %.1fs", job.spec.job_id, quiet)
        elif not job.warned_silent:
            job.silence = self._loop.call_later(self._heartbeat_s - quiet, self._check_silent, job)

    # ---- internals: events from workers (run on the loop) -----------------------------

    def _on_event(self, slot: WorkerSlot, event: JobEvent) -> None:
        if slot.retired and not isinstance(event, Ready):
            self._counts["late"] += 1
            _log.debug("late event %s from retired slot %d", event.kind, slot.index)
            return
        if isinstance(event, Ready):
            slot.ready = True
            _log.info("slot %d: worker ready pid=%d", slot.index, event.pid)
            self._dispatch()
            return
        job = self._jobs.get(event.job_id)
        if job is None or job.state.is_terminal or job.slot is not slot:
            self._counts["late"] += 1
            _log.debug("late %s event for job %s dropped", event.kind, event.job_id)
            return
        job.last_event = self._clock.monotonic()
        match event:
            case Started():
                _log.debug("job %s: task entered", event.job_id)
            case Progress():
                self._on_progress(job, event)
            case Done():
                self._on_done(job, event)
            case Failed():
                self._finish(job, JobState.FAILED, error=event.error, why=event.error.detail)
            case Cancelled():
                self._finish(
                    job,
                    job.outcome.terminal_state
                    if job.outcome is not Outcome.NONE
                    else JobState.CANCELLED,
                    why="(acknowledged)",
                )

    def _on_progress(self, job: _Job, event: Progress) -> None:
        if event.fraction < job.last_fraction:
            self._counts["coalesced"] += 1
            _log.debug("job %s: non-monotonic progress dropped", job.spec.job_id)
            return
        job.last_fraction = event.fraction
        if job.state is JobState.RUNNING:
            self._transition(job, JobState.PROGRESSING, "first progress")
        if event.partial is not None and self._is_current(job):
            self._emit(job, ResultState.REFINING, event.fraction, event.partial)
        elif event.partial is not None:
            self._counts["discarded"] += 1
            _log.debug("job %s: partial discarded (not current)", job.spec.job_id)

    def _on_done(self, job: _Job, event: Done) -> None:
        current = self._is_current(job) and job.outcome is Outcome.NONE
        if current:
            self._emit(job, ResultState.FINAL, 1.0, event.result)
        else:
            self._counts["discarded"] += 1
            _log.debug("job %s: result discarded (superseded or cancelled)", job.spec.job_id)
        self._finish(
            job,
            JobState.DONE,
            result=event.result if current else None,
            why=f"run_ms={event.run_ms:.1f}",
        )

    def _on_death(self, slot: WorkerSlot, pid: int | None, code: int | None) -> None:
        if slot.retired or slot not in self._slots:
            _log.debug("slot %d: expected worker exit pid=%s code=%s", slot.index, pid, code)
            return
        _log.error("slot %d: worker crashed pid=%s exit_code=%s", slot.index, pid, code)
        slot.retired = True
        job = self._jobs.get(slot.job_id) if slot.job_id is not None else None
        if job is not None and not job.state.is_terminal:
            if job.outcome is not Outcome.NONE:
                self._finish(job, job.outcome.terminal_state, why="(worker died while stopping)")
            else:
                err = JobError(code=JobCode.WORKER_CRASHED, detail=f"pid={pid} exit_code={code}")
                self._finish(job, JobState.FAILED, error=err, why=err.detail)
        self._replace(slot)

    # ---- internals: results -----------------------------------------------------------

    def _is_current(self, job: _Job) -> bool:
        return self._current.get(job.spec.key) == job.spec.job_id

    def _emit(
        self,
        job: _Job,
        state: ResultState,
        progress: float,
        value: dict[str, object] | None,
        *,
        data_version: int | None = None,
    ) -> None:
        key = job.spec.key
        dv = job.spec.data_version if data_version is None else data_version
        if dv < self._key_version.get(key, 0):
            self._counts["discarded"] += 1
            _log.debug("key %s: envelope for old dv=%d dropped", key, dv)
            return
        self._publish(key, dv, state, progress, job.spec.job_id, value)

    def _publish(
        self,
        key: JobKey,
        dv: int,
        state: ResultState,
        progress: float,
        job_id: UUID | None,
        value: dict[str, object] | None,
    ) -> None:
        version = self._result_version.get(key, 0) + 1
        self._result_version[key] = version
        env = ResultEnvelope(
            key=key, data_version=dv, result_version=version, state=state,
            progress=progress, job_id=job_id, value=value, emitted_ns=self._clock.time_ns(),
        )  # fmt: skip
        self._latest[key] = env
        _log.debug("key %s: envelope dv=%d rv=%d %s", key, dv, version, state)
        if self._sink is not None:
            self._call(self._sink, env)

    def _mark_stale(self, key: JobKey, data_version: int) -> None:
        last = self._latest.get(key)
        if last is None:
            return
        self._publish(key, data_version, ResultState.STALE, last.progress, last.job_id, last.value)

    def _call(self, fn: Callable[[_T], None], arg: _T) -> None:
        """Invoke a user callback; its failure must not corrupt manager state."""
        try:
            fn(arg)
        except Exception:
            _log.exception("callback %r raised", fn)
