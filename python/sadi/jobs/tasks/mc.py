"""Progressive Monte Carlo job: the interval tightens as batches accumulate (tasks.md)."""

# frob:ticket 01M6W7R3G88NFY3N76MPX6X3ZQ
from __future__ import annotations

import importlib
import math
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field
from typani import Err, Ok, Result

from sadi.jobs.pool import CancelToken
from sadi.jobs.tasks._drive import Steps, TaskError, Tick, drive
from sadi.logging_setup import get_logger
from sadi.uncertainty.montecarlo import (
    DEFAULT_BATCH,
    Marginal,
    McEstimate,
    McSampler,
)

_log = get_logger(__name__)

#: 95% two-sided normal quantile for the half-width of the mean.
_Z95 = 1.959963984540054


class McJobInputs(BaseModel):
    """Validated inputs of the MC task; `fn` is an importable `module:function` path."""

    model_config = ConfigDict(frozen=True)

    fn: str
    means: list[float]
    cov: list[list[float]]
    seed: int
    target: int = Field(ge=2)
    batch_size: int = Field(default=DEFAULT_BATCH, ge=1)
    batches_per_tick: int = Field(default=1, ge=1)
    marginals: list[Marginal] | None = None
    dofs: list[float | None] | None = None


def _resolve_fn(path: str) -> Result[Callable[..., object], TaskError]:
    """Import `module:function`; Err(BadFunction) if the path is malformed or unimportable."""
    module_name, sep, attr = path.partition(":")
    if not sep or not module_name or not attr:
        _log.warning("mc job: bad function path %r", path)
        return Err(TaskError.BadFunction)
    out = Result.catch(
        lambda: getattr(importlib.import_module(module_name), attr),
        ImportError,
        AttributeError,
        on_error=lambda exc: TaskError.BadFunction,
    )
    if isinstance(out, Err):
        _log.warning("mc job: cannot import %r", path)
    return out


def partial_of(est: McEstimate, target: int) -> dict[str, object]:
    """Serialise an estimate plus its progress and 95% half-width of the mean for the stream."""
    out: dict[str, object] = dict(est.model_dump())
    out["target"] = target
    out["halfwidth_mean"] = _Z95 * est.se_mean
    return out


def mc_steps(raw: dict[str, object]) -> Steps:
    """Core of the MC job as a generator: one `Tick` per chunk of batches, then the result.

    Batch k always uses stream (seed, k), so the final estimate equals a single-shot
    `McSampler.run_to(target)` with the same seed. The cancel flag sent in stops the run.
    """
    parsed = Result.catch(
        lambda: McJobInputs.model_validate(raw),
        Exception,
        on_error=lambda exc: TaskError.BadInputs,
    )
    if isinstance(parsed, Err):
        _log.warning("mc job: invalid inputs")
        return Err(parsed.danger_err)
    inp = parsed.danger_ok
    fn = _resolve_fn(inp.fn)
    if isinstance(fn, Err):
        return Err(fn.danger_err)
    made = McSampler.create(
        fn.danger_ok,
        inp.means,
        inp.cov,
        seed=inp.seed,
        marginals=inp.marginals,
        dofs=inp.dofs,
        batch_size=inp.batch_size,
    )
    if isinstance(made, Err):
        _log.warning("mc job: sampler rejected: %s", made.danger_err)
        return Err(TaskError.BadInputs)
    sampler = made.danger_ok
    chunk = inp.batch_size * inp.batches_per_tick
    total_batches = math.ceil(inp.target / inp.batch_size)
    goal = total_batches * inp.batch_size
    _log.info("mc job: seed=%d target=%d goal=%d chunk=%d", inp.seed, inp.target, goal, chunk)
    cancelled = False
    est: McEstimate | None = None
    while sampler.n < goal and not cancelled:
        upto = min(goal, max(2, sampler.n + chunk))
        run = sampler.run_to(upto)
        if isinstance(run, Err):
            _log.error("mc job: run failed at n=%d: %s", sampler.n, run.danger_err)
            return Err(TaskError.Compute)
        est = run.danger_ok
        cancelled = yield Tick(fraction=est.n / goal, partial=partial_of(est, inp.target))
    if est is None or cancelled:
        return Ok({})
    return Ok(partial_of(est, inp.target))


def run_mc(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Worker entry point (`sadi.jobs.tasks.mc:run_mc`): drive `mc_steps` under the token."""
    return drive(mc_steps(inputs), token, "mc job")
