"""Progressive GP fit and next-point suggestion job: best-so-far fit after each lengthscale."""

# frob:ticket 01M6W7R3G88NFY3N76MPX6X3ZQ
from __future__ import annotations

import math
from typing import cast

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field
from scipy import linalg
from typani import Err, Ok, Result

from sadi.jobs.pool import CancelToken
from sadi.jobs.tasks._drive import Steps, TaskError, Tick, drive
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

_JITTER = 1e-9


class GpJobInputs(BaseModel):
    """Validated GP job inputs: observations `x` (n rows of d) and `y` (n), plus candidates."""

    model_config = ConfigDict(frozen=True)

    x: list[list[float]] = Field(min_length=1)
    y: list[float] = Field(min_length=1)
    candidates: list[list[float]] = Field(default_factory=list)
    noise: float = Field(default=1e-4, gt=0.0)
    lengthscales: list[float] = Field(
        default_factory=lambda: [float(v) for v in np.geomspace(0.05, 5.0, 12)], min_length=1
    )


def _rbf(a: NDArray[np.float64], b: NDArray[np.float64], ls: float) -> NDArray[np.float64]:
    """Unit-variance squared-exponential kernel matrix between rows of `a` and `b`."""
    d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
    return np.exp(-0.5 * d2 / (ls * ls))


def _log_marginal(fit: dict[str, object]) -> float:
    """Read the log marginal likelihood out of a fit mapping."""
    return float(cast(float, fit["log_marginal"]))


def _fit_one(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    cand: NDArray[np.float64],
    ls: float,
    noise: float,
) -> Result[dict[str, object], TaskError]:
    """Fit a zero-mean GP at one lengthscale: log marginal likelihood and candidate sd."""
    var = max(float(np.var(y)), 1e-12)
    k = var * _rbf(x, x, ls) + (noise + _JITTER) * np.eye(len(x))
    chol = Result.catch(
        lambda: linalg.cho_factor(k, lower=True), Exception, on_error=lambda exc: TaskError.Compute
    )
    if isinstance(chol, Err):
        _log.warning("gp job: kernel not positive definite at ls=%g", ls)
        return Err(chol.danger_err)
    c = chol.danger_ok
    alpha = linalg.cho_solve(c, y)
    lml = float(
        -0.5 * y @ alpha - np.log(np.diag(c[0])).sum() - 0.5 * len(y) * math.log(2.0 * math.pi)
    )
    out: dict[str, object] = {"lengthscale": ls, "signal_var": var, "log_marginal": lml}
    if len(cand):
        ks = var * _rbf(cand, x, ls)
        v = linalg.cho_solve(c, ks.T)
        sd = np.sqrt(np.clip(var - (ks * v.T).sum(axis=1), 0.0, None))
        best = int(np.argmax(sd))
        out["suggestion"] = {"index": best, "point": cand[best].tolist(), "sd": float(sd[best])}
    return Ok(out)


def gp_steps(raw: dict[str, object]) -> Steps:
    """Core of the GP job as a generator: one `Tick` per lengthscale with the best fit so far.

    The suggestion is the candidate of largest posterior sd under the best-likelihood fit.
    A lengthscale whose kernel is singular is skipped; Err only if all of them are.
    """
    parsed = Result.catch(
        lambda: GpJobInputs.model_validate(raw),
        Exception,
        on_error=lambda exc: TaskError.BadInputs,
    )
    if isinstance(parsed, Err):
        _log.warning("gp job: invalid inputs")
        return Err(parsed.danger_err)
    inp = parsed.danger_ok
    dim = len(inp.x[0])
    if dim == 0 or any(len(r) != dim for r in (*inp.x, *inp.candidates)):
        _log.warning("gp job: ragged or empty rows")
        return Err(TaskError.BadInputs)
    x = np.asarray(inp.x, dtype=float)
    y = np.asarray(inp.y, dtype=float)
    cand = np.asarray(inp.candidates, dtype=float).reshape(len(inp.candidates), dim)
    bad = (
        x.ndim != 2
        or len(x) != len(y)
        or (len(cand) and cand.shape[1] != x.shape[1])
        or not (np.all(np.isfinite(x)) and np.all(np.isfinite(y)))
    )
    if bad:
        _log.warning("gp job: shape mismatch or non-finite data")
        return Err(TaskError.BadInputs)
    n = len(inp.lengthscales)
    _log.info("gp job: n=%d d=%d candidates=%d lengthscales=%d", len(x), x.shape[1], len(cand), n)
    best: dict[str, object] | None = None
    for i, ls in enumerate(inp.lengthscales):
        fit = _fit_one(x, y, cand, ls, inp.noise)
        if isinstance(fit, Ok):
            got = fit.danger_ok
            if best is None or _log_marginal(got) > _log_marginal(best):
                best = got
                _log.debug("gp job: new best ls=%g", ls)
        if best is None:
            continue
        if (yield Tick(fraction=(i + 1) / n, partial=dict(best))):
            return Ok({})
    if best is None:
        _log.error("gp job: every lengthscale failed")
        return Err(TaskError.Compute)
    return Ok(best)


def run_gp(inputs: dict[str, object], token: CancelToken) -> dict[str, object]:
    """Worker entry point (`sadi.jobs.tasks.gp:run_gp`): drive `gp_steps` under the token."""
    return drive(gp_steps(inputs), token, "gp job")
