"""Shared plumbing for progressive tasks: the step protocol and the worker-side driver."""

# frob:ticket 01M6W7R3G88NFY3N76MPX6X3ZQ
from __future__ import annotations

from collections.abc import Generator
from typing import cast

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Result

from sadi.jobs.pool import CancelToken
from sadi.logging_setup import get_logger

_log = get_logger(__name__)


class TaskError(ErrorSet):
    """Failure modes shared by progressive tasks; the description says what to do next."""

    BadInputs = "Task inputs are missing or malformed; see docs/jobs/tasks.md for the spec"
    BadFunction = "Function path must be 'module:function' and importable in the worker"
    Compute = "The numerical core failed; see the log line before this failure for the cause"


class Tick(BaseModel):
    """One progress point of a task: a fraction in [0, 1] and an intermediate result."""

    model_config = ConfigDict(frozen=True)

    fraction: float
    partial: dict[str, object] | None = None


#: A task core: yields a `Tick` per progress point, receives the cancel flag, returns a Result.
Steps = Generator[Tick, bool, Result[dict[str, object], TaskError]]


def drive(steps: Steps, token: CancelToken, name: str) -> dict[str, object]:
    """Run a task core under `token`, emitting each tick; raise at the worker boundary on Err.

    Returns `{}` when cancelled (the pool then reports Cancelled); an Err result is raised as
    `RuntimeError` because the worker boundary converts exceptions to a Failed event.
    """
    cancelled = False
    try:
        tick = next(steps)
        while True:
            cancelled = token.check(tick.fraction, tick.partial)
            tick = steps.send(cancelled)
    except StopIteration as stop:
        result = cast(Result[dict[str, object], TaskError], stop.value)
    if cancelled:
        _log.info("%s: cancelled; discarding partial work", name)
        return {}
    if isinstance(result, Err):
        _log.error("%s: failed: %s", name, result.danger_err)
        raise RuntimeError(f"{name}: {result.danger_err}")
    _log.info("%s: finished", name)
    return result.danger_ok
