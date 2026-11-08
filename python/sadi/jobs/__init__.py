"""Background job system: latest-wins process pool with cooperative cancel (concurrency.md)."""

from sadi.jobs.manager import JobManager
from sadi.jobs.pool import CancelToken
from sadi.jobs.state import (
    JobId,
    JobKey,
    JobMetrics,
    JobOutcome,
    JobSpec,
    JobState,
    ResultEnvelope,
    ResultState,
)

__all__ = [
    "CancelToken",
    "JobId",
    "JobKey",
    "JobManager",
    "JobMetrics",
    "JobOutcome",
    "JobSpec",
    "JobState",
    "ResultEnvelope",
    "ResultState",
]
