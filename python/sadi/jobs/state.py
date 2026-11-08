"""Job domain types: lifecycle enum, specs, worker events, metrics and result envelopes.

Pure data, no I/O. Implements docs/concurrency.md sections 6, 8 and 9.2; the human-facing
description lives in docs/jobs/jobs.md. Imported by both the manager (parent) and the
worker, so it must never import web or store code.
"""

# frob:ticket 01M6W7R1Z1E430ZNZ51V9NMTHC
from __future__ import annotations

import os
from enum import StrEnum
from typing import Annotated, Literal, NewType, assert_never
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from sadi.core.errors import JobError

#: Seconds a cancelled worker has to acknowledge before it is killed (concurrency.md 7.2).
CANCEL_GRACE_S = 0.5
#: Seconds to wait for a worker to exit after `Shutdown` before killing it.
WORKER_JOIN_S = 2.0
#: Seconds of silence from a RUNNING worker before one WARNING is logged.
WORKER_HEARTBEAT_S = 10.0
#: Default minimum spacing of progress events from one task, in milliseconds.
PROGRESS_MIN_INTERVAL_MS = 100

JobKey = NewType("JobKey", str)
JobId = NewType("JobId", UUID)

Priority = Literal["interactive", "background"]


def default_worker_count() -> int:
    """Return `max(1, min(4, cpu_count - 1))`, the default pool size (concurrency.md 1)."""
    return max(1, min(4, (os.cpu_count() or 2) - 1))


class JobState(StrEnum):
    """Lifecycle state of one job; DONE, FAILED, CANCELLED and SUPERSEDED are terminal."""

    QUEUED = "queued"
    RUNNING = "running"
    PROGRESSING = "progressing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"

    @property
    def is_terminal(self) -> bool:
        """True for states a job never leaves."""
        match self:
            case JobState.QUEUED | JobState.RUNNING | JobState.PROGRESSING:
                return False
            case JobState.DONE | JobState.FAILED | JobState.CANCELLED | JobState.SUPERSEDED:
                return True
            case _:
                assert_never(self)

    @property
    def next_states(self) -> frozenset[JobState]:
        """States reachable from this one (the table in concurrency.md section 6)."""
        match self:
            case JobState.QUEUED:
                return frozenset({JobState.RUNNING, JobState.SUPERSEDED, JobState.CANCELLED})
            case JobState.RUNNING | JobState.PROGRESSING:
                live = {JobState.DONE, JobState.FAILED, JobState.CANCELLED, JobState.SUPERSEDED}
                if self is JobState.RUNNING:
                    live.add(JobState.PROGRESSING)
                return frozenset(live)
            case JobState.DONE | JobState.FAILED | JobState.CANCELLED | JobState.SUPERSEDED:
                return frozenset()
            case _:
                assert_never(self)

    def can_go(self, to: JobState) -> bool:
        """True if the transition self -> to is allowed."""
        return to in self.next_states


class Outcome(StrEnum):
    """Why a live job is being stopped; decides its terminal state."""

    NONE = "none"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"

    @property
    def terminal_state(self) -> JobState:
        """Terminal JobState a stopped job lands in."""
        match self:
            case Outcome.CANCELLED:
                return JobState.CANCELLED
            case Outcome.SUPERSEDED:
                return JobState.SUPERSEDED
            case Outcome.NONE:
                return JobState.DONE
            case _:
                assert_never(self)


class JobSpec(BaseModel):
    """One unit of CPU work; `task` is an import path `module:function`, never pickled."""

    model_config = ConfigDict(frozen=True)

    job_id: UUID
    key: JobKey
    data_version: int
    task: str
    inputs: dict[str, object] = Field(default_factory=dict)
    priority: Priority = "background"
    progress_interval_ms: int = Field(default=PROGRESS_MIN_INTERVAL_MS, ge=0)


# ---- worker -> parent events (concurrency.md section 8) ----------------------------------


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True)


class Ready(_Event):
    """Worker is up and idle."""

    kind: Literal["ready"] = "ready"
    pid: int
    slot: int


class Started(_Event):
    """Task function entered."""

    kind: Literal["started"] = "started"
    job_id: UUID


class Progress(_Event):
    """Throttled progress with an optional intermediate result."""

    kind: Literal["progress"] = "progress"
    job_id: UUID
    fraction: float = Field(ge=0.0, le=1.0)
    partial: dict[str, object] | None = None
    mono_ns: int


class Done(_Event):
    """Task finished; carries the result by value."""

    kind: Literal["done"] = "done"
    job_id: UUID
    result: dict[str, object]
    run_ms: float


class Failed(_Event):
    """Task raised or could not be loaded."""

    kind: Literal["failed"] = "failed"
    job_id: UUID
    error: JobError


class Cancelled(_Event):
    """Task stopped in response to a cancel request."""

    kind: Literal["cancelled"] = "cancelled"
    job_id: UUID


JobEvent = Annotated[
    Ready | Started | Progress | Done | Failed | Cancelled,
    Field(discriminator="kind"),
]


# ---- results (concurrency.md section 9.2) -------------------------------------------------


class ResultState(StrEnum):
    """Freshness of a published value."""

    ANALYTIC = "analytic"
    REFINING = "refining"
    FINAL = "final"
    STALE = "stale"


class ResultEnvelope(BaseModel):
    """Versioned value for one key; clients accept it iff (data_version, result_version) grows."""

    model_config = ConfigDict(frozen=True)

    protocol_version: Literal[1] = 1
    key: JobKey
    data_version: int
    result_version: int
    state: ResultState
    progress: float = Field(ge=0.0, le=1.0)
    job_id: UUID | None = None
    value: dict[str, object] | None = None
    emitted_ns: int


class JobOutcome(BaseModel):
    """Final report of a terminal job: state, typed error, kill flag and result (if any)."""

    model_config = ConfigDict(frozen=True)

    job_id: UUID
    key: JobKey
    data_version: int
    state: JobState
    killed: bool = False
    discarded: bool = False
    error: JobError | None = None
    result: dict[str, object] | None = None


class JobMetrics(BaseModel):
    """Immutable counters snapshot (concurrency.md section 5)."""

    model_config = ConfigDict(frozen=True)

    submitted_total: int = 0
    done_total: int = 0
    failed_total: int = 0
    cancelled_total: int = 0
    superseded_total: int = 0
    killed_total: int = 0
    worker_restarts: int = 0
    late_events: int = 0
    progress_coalesced: int = 0
    silent_workers: int = 0
    discarded_results: int = 0
    queued: int = 0
    running: int = 0
