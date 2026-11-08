"""Deterministic job test harness: fake clock and loop, scripted workers, seeded interleaver.

Implements docs/concurrency.md section 14 for the job system. `JobHarness` drives a real
`JobManager` with no processes, threads or sleeps: time is a `FakeClock`, the asyncio loop is a
`FakeLoop` whose timers and posted callbacks only run when the test says so, and workers are
`FakeSlot`s that run generator "scripts" one step at a time. `Interleaver` picks the next actor
with a seeded RNG and records a plain-list trace that `replay` re-executes exactly.
Human-facing recipe: docs/jobs/testing.md. Test-support code: never imported by production.
"""

# frob:ticket 01M6W7R2GTD88HAHEJ4VAX9DG6
from __future__ import annotations

import asyncio
import heapq
import itertools
import random
from collections import deque
from collections.abc import Callable, Generator
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.core.errors import JobCode, JobError
from sadi.jobs import manager as manager_module
from sadi.jobs.manager import JobManager
from sadi.jobs.pool import WorkerSlot
from sadi.jobs.state import (
    Cancelled,
    Done,
    Failed,
    JobEvent,
    JobKey,
    JobOutcome,
    JobSpec,
    Priority,
    Progress,
    Ready,
    ResultEnvelope,
    Started,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

_NS = 1_000_000_000
#: Fake pid base: slot `i` incarnation `n` reports pid `_PID_BASE + 100*i + n`.
_PID_BASE = 10_000


class HarnessError(BaseModel):
    """Misuse of the harness by a test (stepping an idle slot, replaying a stale trace)."""

    model_config = ConfigDict(frozen=True)

    detail: str


class Step(BaseModel):
    """One yield point of a scripted task: a progress report the test releases on demand."""

    model_config = ConfigDict(frozen=True)

    fraction: float
    partial: dict[str, object] | None = None


#: A scripted task. Each `yield Step(...)` is a `token.check`; the value sent back in is the
#: cancel flag (True once a Cancel arrived). The return value is the result dict; raising fails
#: the job. Registered under a name and referenced by `JobSpec.task`.
Script = Callable[[dict[str, object]], Generator[Step, bool, dict[str, object]]]


class FakeTimer:
    """Stand-in for `asyncio.TimerHandle`; `cancel` removes it from the clock's schedule."""

    def __init__(self, when_ns: int, seq: int, fn: Callable[..., object], args: tuple[object, ...]):
        self.when_ns = when_ns
        self.seq = seq
        self._fn = fn
        self._args = args
        self.cancelled = False

    def __lt__(self, other: FakeTimer) -> bool:
        return (self.when_ns, self.seq) < (other.when_ns, other.seq)

    def cancel(self) -> None:
        """Mark the timer dead; it is skipped when due."""
        self.cancelled = True

    def fire(self) -> None:
        """Run the callback."""
        self._fn(*self._args)


class FakeClock:
    """Monotonic fake time in integer nanoseconds; only `advance` moves it."""

    def __init__(self, start_ns: int = 0) -> None:
        self._now_ns = start_ns
        self._timers: list[FakeTimer] = []
        self._seq = itertools.count()
        self._loop: FakeLoop | None = None

    def monotonic_ns(self) -> int:
        """Current fake time."""
        return self._now_ns

    def monotonic(self) -> float:
        """Current fake time in seconds."""
        return self._now_ns / _NS

    def sleep(self, seconds: float) -> None:
        """Advance time instead of blocking, so sleeping code under test never waits."""
        self.advance(seconds)

    def deadline(self, seconds: float) -> int:
        """Absolute fake time `seconds` from now."""
        return self._now_ns + round(seconds * _NS)

    def schedule(self, delay_s: float, fn: Callable[..., object], *args: object) -> FakeTimer:
        """Register a timer; it fires during `advance` once its time is reached."""
        timer = FakeTimer(self.deadline(max(0.0, delay_s)), next(self._seq), fn, args)
        heapq.heappush(self._timers, timer)
        _log.debug("clock: timer +%.3fs scheduled (%d pending)", delay_s, len(self._timers))
        return timer

    def pending_timers(self) -> int:
        """Number of live (not cancelled) timers."""
        return sum(1 for t in self._timers if not t.cancelled)

    def advance(self, seconds: float) -> int:
        """Move time forward, firing due timers in order (draining the loop after each)."""
        target = self._now_ns + round(seconds * _NS)
        fired = 0
        while True:
            while self._timers and self._timers[0].cancelled:
                heapq.heappop(self._timers)
            if not self._timers or self._timers[0].when_ns > target:
                break
            timer = heapq.heappop(self._timers)
            self._now_ns = max(self._now_ns, timer.when_ns)
            _log.debug("clock: firing timer at t=%.3fs", self.monotonic())
            timer.fire()
            fired += 1
            if self._loop is not None:
                self._loop.drain()
        self._now_ns = target
        return fired


class FakeLoop:
    """The slice of the asyncio loop `JobManager` uses, with every callback under test control."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        clock._loop = self  # noqa: SLF001 - paired objects
        self._ready: deque[tuple[Callable[..., object], tuple[object, ...]]] = deque()

    def time(self) -> float:
        """Fake loop time in seconds."""
        return self.clock.monotonic()

    def call_later(self, delay: float, fn: Callable[..., object], *args: object) -> FakeTimer:
        """Schedule `fn` on the fake clock."""
        return self.clock.schedule(delay, fn, *args)

    def call_soon_threadsafe(self, fn: Callable[..., object], *args: object) -> None:
        """Queue `fn` for the next `drain` (the RecordingPoster of concurrency.md 14.1)."""
        self._ready.append((fn, args))

    call_soon = call_soon_threadsafe

    def create_future(self) -> object:
        """Unsupported: harness tests use `on_outcome`, not awaitables (programmer error)."""
        msg = "FakeLoop has no futures; collect results via JobHarness.outcomes"
        raise NotImplementedError(msg)

    def pending(self) -> int:
        """Number of posted callbacks waiting for `drain`."""
        return len(self._ready)

    def drain(self, limit: int | None = None) -> int:
        """Run posted callbacks (FIFO) including ones they post; return how many ran."""
        ran = 0
        while self._ready and (limit is None or ran < limit):
            fn, args = self._ready.popleft()
            fn(*args)
            ran += 1
        return ran


class FakeSlot:
    """Drop-in for `WorkerSlot`: runs scripted tasks in-process, one `step` at a time."""

    def __init__(
        self,
        index: int,
        incarnation: int,
        harness: JobHarness,
        on_event: Callable[[Any, JobEvent], None],
        on_death: Callable[[Any, int | None, int | None], None],
    ) -> None:
        self.index = index
        self.incarnation = incarnation
        self.ready = False
        self.retired = False
        self.job_id: UUID | None = None
        self.coalesced = 0
        self.killed = False
        self.cancel_requests: list[UUID] = []
        self._h = harness
        self._on_event = on_event
        self._on_death = on_death
        self._spec: JobSpec | None = None
        self._gen: Generator[Step, bool, dict[str, object]] | None = None
        self._started_at_ns = 0
        self._began = False
        self._primed = False
        self._cancel_flag = False
        self._pending: Progress | None = None
        self._pid = _PID_BASE + 100 * index + incarnation
        self._post(Ready(pid=self._pid, slot=index))
        _log.info("fake slot %d.%d: spawned pid=%d", index, incarnation, self._pid)

    @property
    def pid(self) -> int | None:
        """Fake pid of this incarnation."""
        return self._pid

    @property
    def busy(self) -> bool:
        """True while a scripted job is loaded and has not terminated."""
        return self._spec is not None

    def send_run(self, spec: JobSpec) -> Result[None, JobError]:
        """Load `spec`; the task only advances on `step`."""
        if self.job_id is not None:
            return Err(JobError(code=JobCode.SLOT_BUSY, detail=f"slot {self.index}"))
        self.job_id = spec.job_id
        self._spec = spec
        self._gen = None
        self._began = False
        self._cancel_flag = False
        _log.debug("fake slot %d: run %s task=%s", self.index, spec.job_id, spec.task)
        return Ok(None)

    def send_cancel(self, job_id: UUID) -> None:
        """Record a Cancel; a script sees it as `True` from its next yield on."""
        self.cancel_requests.append(job_id)
        if self._spec is not None and self._spec.job_id == job_id:
            self._cancel_flag = True
        _log.debug("fake slot %d: cancel %s (flag=%s)", self.index, job_id, self._cancel_flag)

    def kill(self) -> None:
        """Hard kill: retire the slot and drop the script without emitting anything."""
        self.retired = True
        self.killed = True
        self._drop()
        _log.warning("fake slot %d.%d: killed", self.index, self.incarnation)

    def request_shutdown(self) -> None:
        """Retire the slot."""
        self.retired = True

    def join(self, timeout_s: float = 0.0) -> bool:
        """Nothing to join; always polite."""
        return True

    def pending_coalesced(self) -> int:
        """Progress events replaced before the loop saw them."""
        return self.coalesced

    def take_progress(self) -> Progress | None:
        """Loop side: take the newest pending Progress."""
        event, self._pending = self._pending, None
        return event

    def crash(self, exit_code: int = -9) -> None:
        """Simulate the worker dying (pipe EOF): posts the death callback, drops the script."""
        self._drop()
        _log.warning(
            "fake slot %d.%d: crashed exit_code=%d", self.index, self.incarnation, exit_code
        )
        self._h.loop.call_soon_threadsafe(self._on_death, self, self._pid, exit_code)

    def step(self) -> Result[str, HarnessError]:
        """Advance the loaded script to its next yield; return a short label of what happened."""
        spec = self._spec
        if spec is None:
            return Err(HarnessError(detail=f"slot {self.index} has no job to step"))
        if not self._began:
            self._began = True
            script = self._h.scripts.get(spec.task)
            if script is None:
                err = JobError(code=JobCode.TASK_FAILED, detail=f"unknown task {spec.task!r}")
                self._post(Failed(job_id=spec.job_id, error=err))
                self._drop()
                return Ok("failed:unknown-task")
            self._gen = script(dict(spec.inputs))
            self._started_at_ns = self._h.clock.monotonic_ns()
            self._post(Started(job_id=spec.job_id))
            return Ok("started")
        gen = self._gen
        assert gen is not None, "script exists once Started was emitted"
        try:
            step = gen.send(self._cancel_flag) if self._primed else next(gen)
        except StopIteration as stop:
            return Ok(self._finish(spec, cast("dict[str, object]", stop.value or {})))
        except Exception as exc:  # noqa: BLE001  # frob:waive TYP007 scripts are untrusted like real tasks; the failure is reported as a Failed event
            err = JobError(code=JobCode.TASK_FAILED, detail=f"{spec.task}: {exc!r}")
            self._post(Failed(job_id=spec.job_id, error=err))
            self._drop()
            return Ok("failed")
        self._primed = True
        self._emit_progress(spec, step)
        return Ok(f"progress:{step.fraction:g}")

    def _finish(self, spec: JobSpec, result: dict[str, object]) -> str:
        if self._cancel_flag:
            self._post(Cancelled(job_id=spec.job_id))
            label = "cancelled"
        else:
            run_ms = (self._h.clock.monotonic_ns() - self._started_at_ns) / 1e6
            self._post(Done(job_id=spec.job_id, result=result, run_ms=run_ms))
            label = "done"
        self._drop()
        return label

    def _emit_progress(self, spec: JobSpec, step: Step) -> None:
        event = Progress(
            job_id=spec.job_id,
            fraction=step.fraction,
            partial=step.partial,
            mono_ns=self._h.clock.monotonic_ns(),
        )
        replaced = self._pending is not None
        self._pending = event
        if replaced:
            self.coalesced += 1
            _log.debug("fake slot %d: progress coalesced (%d)", self.index, self.coalesced)
            return
        self._h.loop.call_soon_threadsafe(self._drain)

    def _drain(self) -> None:
        event = self.take_progress()
        if event is not None:
            self._on_event(self, event)

    def _post(self, event: JobEvent) -> None:
        self._h.loop.call_soon_threadsafe(self._on_event, self, event)

    def _drop(self) -> None:
        if self._gen is not None:
            self._gen.close()
        self._gen = None
        self._spec = None
        self._primed = False


class _TimeShim:
    """Replacement for the `time` module inside `sadi.jobs.manager` (reads the fake clock)."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock

    def monotonic(self) -> float:
        """Fake monotonic seconds."""
        return self._clock.monotonic()

    def time_ns(self) -> int:
        """Fake wall-clock nanoseconds (same as monotonic; epoch is test start)."""
        return self._clock.monotonic_ns()


class _HarnessManager(JobManager):
    """JobManager whose workers are `FakeSlot`s created through the harness."""

    def __init__(
        self,
        harness: JobHarness,
        workers: int,
        *,
        grace_s: float,
        heartbeat_s: float,
        sink: Callable[[ResultEnvelope], None],
        on_outcome: Callable[[JobOutcome], None],
    ) -> None:
        self._harness = harness
        super().__init__(
            workers,
            loop=cast("asyncio.AbstractEventLoop", harness.loop),
            grace_s=grace_s,
            heartbeat_s=heartbeat_s,
            sink=sink,
            on_outcome=on_outcome,
        )

    def _spawn(self, index: int) -> WorkerSlot:
        slot = self._harness.spawn_slot(index, self._on_event, self._on_death)
        return cast("WorkerSlot", slot)


class JobHarness:
    """A real `JobManager` wired to a fake clock, fake loop and scripted workers."""

    def __init__(
        self, workers: int = 1, *, grace_s: float = 0.5, heartbeat_s: float = 10.0
    ) -> None:
        self.clock = FakeClock()
        self.loop = FakeLoop(self.clock)
        self.scripts: dict[str, Script] = {}
        self.slots: list[FakeSlot] = []
        self.outcomes: list[JobOutcome] = []
        self.envelopes: list[ResultEnvelope] = []
        self._incarnations: dict[int, int] = {}
        self.manager = _HarnessManager(
            self,
            workers,
            grace_s=grace_s,
            heartbeat_s=heartbeat_s,
            sink=self.envelopes.append,
            on_outcome=self.outcomes.append,
        )
        self._real_time = manager_module.time
        vars(manager_module)["time"] = _TimeShim(self.clock)
        _log.info("harness: created with %d workers", workers)

    def close(self) -> None:
        """Restore the real `time` module in `sadi.jobs.manager`; call once per harness."""
        vars(manager_module)["time"] = self._real_time
        _log.info("harness: closed")

    def register(self, name: str, script: Script) -> str:
        """Register a script; returns the name to use as `JobSpec.task`."""
        self.scripts[name] = script
        return name

    def spawn_slot(
        self,
        index: int,
        on_event: Callable[[Any, JobEvent], None],
        on_death: Callable[[Any, int | None, int | None], None],
    ) -> FakeSlot:
        """Create the next incarnation of slot `index` (called by the manager)."""
        n = self._incarnations.get(index, 0)
        self._incarnations[index] = n + 1
        slot = FakeSlot(index, n, self, on_event, on_death)
        self.slots.append(slot)
        return slot

    def start(self) -> None:
        """Start the manager and deliver the workers' Ready events."""
        self.manager.start()
        self.settle()

    def live_slot(self, index: int) -> FakeSlot:
        """Newest incarnation of slot `index`."""
        return next(s for s in reversed(self.slots) if s.index == index)

    def settle(self) -> int:
        """Drain posted callbacks until none remain; return how many ran."""
        return self.loop.drain()

    def step(self, index: int) -> Result[str, HarnessError]:
        """Step slot `index` once, then deliver everything that step posted."""
        res = self.live_slot(index).step()
        self.settle()
        return res

    def run_slot(self, index: int, max_steps: int = 1000) -> Result[list[str], HarnessError]:
        """Step slot `index` until its job terminates."""
        labels: list[str] = []
        for _ in range(max_steps):
            slot = self.live_slot(index)
            if not slot.busy:
                return Ok(labels)
            match self.step(index):
                case Err(e):
                    return Err(e)
                case Ok(label):
                    labels.append(label)
        return Err(HarnessError(detail=f"slot {index} still busy after {max_steps} steps"))

    def advance(self, seconds: float) -> int:
        """Advance the fake clock (firing grace and heartbeat timers) and deliver callbacks."""
        fired = self.clock.advance(seconds)
        self.settle()
        return fired

    def runnable(self) -> list[str]:
        """Names of actors that can act now: `drain` and `step:<slot>` (sorted, stable)."""
        names = ["drain"] if self.loop.pending() else []
        names += [f"step:{s.index}" for s in self.slots if s.busy and not s.retired]
        return sorted(names)

    def act(self, name: str) -> Result[str, HarnessError]:
        """Perform one named actor action; the unit recorded in an interleaving trace."""
        if name not in self.runnable():
            return Err(HarnessError(detail=f"actor {name!r} not runnable; have {self.runnable()}"))
        if name == "drain":
            return Ok(f"drain:{self.loop.drain(limit=1)}")
        return self.live_slot(int(name.split(":")[1])).step()


def make_spec(
    n: int,
    key: str = "k",
    task: str = "t",
    *,
    data_version: int = 1,
    priority: Priority = "background",
    **inputs: object,
) -> JobSpec:
    """Build a `JobSpec` with the deterministic job id `UUID(int=n)`."""
    return JobSpec(
        job_id=UUID(int=n),
        key=JobKey(key),
        data_version=data_version,
        task=task,
        inputs=dict(inputs),
        priority=priority,
    )


class Interleaver:
    """Seeded choice among runnable actors; `trace` is a plain list so it can be stored."""

    def __init__(self, harness: JobHarness, seed: int) -> None:
        self.harness = harness
        self.seed = seed
        self.trace: list[str] = []
        self._rng = random.Random(seed)  # noqa: S311 - determinism, not security

    def tick(self) -> Result[str | None, HarnessError]:
        """Pick one runnable actor with the seeded RNG and run it; Ok(None) if none runnable."""
        names = self.harness.runnable()
        if not names:
            return Ok(None)
        name = self._rng.choice(names)
        self.trace.append(name)
        acted = self.harness.act(name)
        if isinstance(acted, Err):
            return Err(acted.error)
        return Ok(name)

    def run_until_idle(self, max_ticks: int = 10_000) -> Result[list[str], HarnessError]:
        """Tick until nothing is runnable; Err if `max_ticks` is exceeded (livelock)."""
        for _ in range(max_ticks):
            match self.tick():
                case Err(e):
                    return Err(e)
                case Ok(None):
                    _log.info(
                        "interleaver seed=%d: idle after %d actions", self.seed, len(self.trace)
                    )
                    return Ok(list(self.trace))
                case Ok():
                    pass
        return Err(HarnessError(detail=f"seed {self.seed}: not idle after {max_ticks} ticks"))

    @staticmethod
    def replay(harness: JobHarness, trace: list[str]) -> Result[None, HarnessError]:
        """Re-execute a recorded trace exactly; Err at the first action that is not runnable."""
        for i, name in enumerate(trace):
            match harness.act(name):
                case Err(e):
                    return Err(HarnessError(detail=f"replay diverged at {i}: {e.detail}"))
                case Ok():
                    pass
        return Ok(None)
