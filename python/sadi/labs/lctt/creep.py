"""LCTT creep fit: strain = a + b*ln(t - t_load) per hold, with uncertainty (pure, no I/O)."""

# frob:ticket 01M6W7R1N7W6ZKBBM4M7NDJSG8

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, Field
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured

_log = get_logger(__name__)


class CreepError(ErrorSet):
    """Malformed or too-short creep hold; the description says what to fix."""

    LengthMismatch = "times and strain must have equal length; pass one strain per timestamp"
    NonFinite = "Samples must be finite; drop or repair NaN/inf readings before fitting"
    NonMonotonicTime = "Timestamps must be strictly increasing; check the acquisition clock"
    BeforeLoad = "All samples must be after the load change; trim samples at or before t_load"
    BadReference = "Reference time must be finite and after t_load"
    HoldTooShort = "Hold too short to fit creep; hold longer or lower min_points/min_decades"
    NotRepresentable = "Fit result could not be built as Measured; check the strain samples"


class CreepConfig(BaseModel):
    """Frozen fit parameters: minimum samples and minimum log-time span (decades)."""

    model_config = {"frozen": True}

    min_points: int = Field(default=5, ge=3, le=1000000, description="Fewest samples per hold")
    min_decades: float = Field(default=0.5, ge=0, le=20, description="Min log10 span of t-t_load")


class CreepFit(BaseModel):
    """Per-hold creep fit: intercept a, log-time slope b, r^2 and strain at the reference time."""

    model_config = {"frozen": True}

    a: Measured
    b: Measured
    r2: float
    n_points: int
    t_ref: float
    strain_at_ref: Measured


def _validate(
    times: Sequence[float], strain: Sequence[float], t_load: float, t_ref: float
) -> CreepError | None:
    """Return the first input problem found, or None."""
    if len(times) != len(strain):
        return CreepError.LengthMismatch
    if not (math.isfinite(t_load) and all(math.isfinite(v) for v in (*times, *strain))):
        return CreepError.NonFinite
    if not math.isfinite(t_ref) or t_ref <= t_load:
        return CreepError.BadReference
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        return CreepError.NonMonotonicTime
    if times and times[0] <= t_load:
        return CreepError.BeforeLoad
    return None


def _measured(value: float, se: float, dof: float) -> Result[Measured, CreepError]:
    """Wrap a fitted quantity as dimensionless Measured with the fit's dof."""
    m = Measured.create(value, se, dof=dof)
    if isinstance(m, Err):
        _log.error("creep quantity not representable: %s", m.danger_err.name)
        return Err(CreepError.NotRepresentable)
    return Ok(m.danger_ok)


def fit_creep(
    times: Sequence[float],
    strain: Sequence[float],
    t_load: float,
    t_ref: float,
    config: CreepConfig | None = None,
) -> Result[CreepFit, CreepError]:
    """Fit strain = a + b*ln(t - t_load) by OLS and extrapolate to t_ref with uncertainty."""
    cfg = config or CreepConfig()
    bad = _validate(times, strain, t_load, t_ref)
    if bad is not None:
        _log.error("creep input rejected: %s", bad.name)
        return Err(bad)
    n = len(times)
    if n < cfg.min_points:
        _log.warning("creep hold too short: %d < %d points", n, cfg.min_points)
        return Err(CreepError.HoldTooShort)
    x = [math.log(t - t_load) for t in times]
    if (x[-1] - x[0]) / math.log(10.0) < cfg.min_decades:
        _log.warning(
            "creep hold spans %.3g decades < %g", (x[-1] - x[0]) / math.log(10), cfg.min_decades
        )
        return Err(CreepError.HoldTooShort)

    xm = sum(x) / n
    ym = sum(strain) / n
    sxx = sum((v - xm) ** 2 for v in x)
    sxy = sum((v - xm) * (w - ym) for v, w in zip(x, strain, strict=True))
    syy = sum((w - ym) ** 2 for w in strain)
    b = sxy / sxx
    a = ym - b * xm
    sse = max(sum((w - a - b * v) ** 2 for v, w in zip(x, strain, strict=True)), 0.0)
    dof = n - 2
    s2 = sse / dof
    se_b = math.sqrt(s2 / sxx)
    se_a = math.sqrt(s2 * (1.0 / n + xm**2 / sxx))
    r2 = 1.0 - sse / syy if syy > 0 else 1.0
    xr = math.log(t_ref - t_load)
    se_ref = math.sqrt(s2 * (1.0 / n + (xr - xm) ** 2 / sxx))

    parts = [_measured(a, se_a, dof), _measured(b, se_b, dof), _measured(a + b * xr, se_ref, dof)]
    for p in parts:
        if isinstance(p, Err):
            return Err(p.danger_err)
    _log.info("creep fit n=%d b=%g a=%g r2=%.4f ref=%g", n, b, a, r2, a + b * xr)
    return Ok(
        CreepFit(
            a=parts[0].danger_ok,
            b=parts[1].danger_ok,
            r2=r2,
            n_points=n,
            t_ref=t_ref,
            strain_at_ref=parts[2].danger_ok,
        )
    )
