"""LCTT settle detector: rolling LVDT drift slope, threshold and minimum dwell (pure, no I/O)."""

# frob:ticket 01M6W7R1KH0MVS56MX07Q9BX19

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured

_log = get_logger(__name__)


class SettleError(ErrorSet):
    """Malformed detector input; the description says what to fix."""

    LengthMismatch = "times and lvdt must have equal length; pass one LVDT sample per timestamp"
    NonFinite = "Samples must be finite; drop or repair NaN/inf readings before detection"
    NonMonotonicTime = "Timestamps must be strictly increasing; check the acquisition clock"
    SlopeUnavailable = "Slope could not be built as Measured; check the window samples"


class NotSettledReason(StrEnum):
    """Why the detector has not (yet) declared the signal settled."""

    InsufficientData = "insufficient_data"
    SlopeAboveThreshold = "slope_above_threshold"
    SlopeUncertain = "slope_uncertain"
    DwellNotReached = "dwell_not_reached"


class SettleConfig(BaseModel):
    """Frozen detector parameters: window, slope threshold, minimum dwell and noise guard."""

    model_config = {"frozen": True}

    window_s: float = Field(gt=0, le=3600, description="Rolling slope window length, seconds")
    threshold: float = Field(gt=0, description="Max |drift rate| to count as settled, V/s")
    min_dwell_s: float = Field(ge=0, le=86400, description="Time the criterion must hold, s")
    min_points: int = Field(default=5, ge=3, le=100000, description="Fewest samples per window")
    unc_factor: float = Field(default=1.0, ge=0, le=10, description="k in |slope| + k*se <= thr")


class SettleResult(BaseModel):
    """Detector verdict: settle index/time, slope with uncertainty, or the reason it has not."""

    model_config = {"frozen": True}

    settled: bool
    settled_index: int | None = None
    settled_time: float | None = None
    confirmed_index: int | None = None
    slope: Measured | None = None
    window_points: int = 0
    reason: NotSettledReason | None = None


def _window_slope(t: Sequence[float], y: Sequence[float]) -> tuple[float, float]:
    """OLS slope and its standard error over one window (se is inf if residuals undefined)."""
    n = len(t)
    tm = sum(t) / n
    ym = sum(y) / n
    sxx = sum((a - tm) ** 2 for a in t)
    sxy = sum((a - tm) * (b - ym) for a, b in zip(t, y, strict=True))
    slope = sxy / sxx
    sse = sum((b - ym - slope * (a - tm)) ** 2 for a, b in zip(t, y, strict=True))
    se = math.sqrt(sse / (n - 2) / sxx)
    return slope, se


def _validate(times: Sequence[float], lvdt: Sequence[float]) -> SettleError | None:
    """Return the first input problem found, or None."""
    if len(times) != len(lvdt):
        return SettleError.LengthMismatch
    if not all(math.isfinite(v) for v in times) or not all(math.isfinite(v) for v in lvdt):
        return SettleError.NonFinite
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        return SettleError.NonMonotonicTime
    return None


def detect_settle(
    times: Sequence[float], lvdt: Sequence[float], config: SettleConfig
) -> Result[SettleResult, SettleError]:
    """Suggest whether the LVDT has settled; never alters data, a human confirms the suggestion."""
    bad = _validate(times, lvdt)
    if bad is not None:
        _log.error("settle input rejected: %s", bad.name)
        return Err(bad)

    n = len(times)
    start = 0
    run_start: int | None = None
    run_slope: tuple[float, float, int] | None = None
    last_slope: tuple[float, float, int] | None = None
    reason = NotSettledReason.InsufficientData
    for i in range(n):
        while times[i] - times[start] > config.window_s:
            start += 1
        npts = i - start + 1
        if npts < config.min_points or times[i] - times[0] < config.window_s:
            run_start = None
            reason = NotSettledReason.InsufficientData
            continue
        slope, se = _window_slope(times[start : i + 1], lvdt[start : i + 1])
        last_slope = (slope, se, npts)
        if abs(slope) > config.threshold:
            run_start, reason = None, NotSettledReason.SlopeAboveThreshold
            continue
        if abs(slope) + config.unc_factor * se > config.threshold:
            run_start, reason = None, NotSettledReason.SlopeUncertain
            continue
        if run_start is None:
            run_start, run_slope = i, (slope, se, npts)
            _log.debug("settle criterion met at index %d (t=%g)", i, times[i])
        if run_slope is not None and times[i] - times[run_start] >= config.min_dwell_s:
            return _build(run_start, i, times, run_slope)
        reason = NotSettledReason.DwellNotReached

    _log.info("not settled after %d samples: %s", n, reason.value)
    if last_slope is None:
        return Ok(SettleResult(settled=False, reason=reason))
    slope_m = _measured(*last_slope)
    if isinstance(slope_m, Err):
        return Err(slope_m.danger_err)
    return Ok(
        SettleResult(
            settled=False, slope=slope_m.danger_ok, window_points=last_slope[2], reason=reason
        )
    )


def _measured(slope: float, se: float, npts: int) -> Result[Measured, SettleError]:
    """Wrap a window slope as Measured in V/s with dof = n - 2."""
    m = Measured.create(slope, se, "V/s", dof=npts - 2)
    if isinstance(m, Err):
        _log.error("slope not representable: %s", m.danger_err.name)
        return Err(SettleError.SlopeUnavailable)
    return Ok(m.danger_ok)


def _build(
    first: int, confirmed: int, times: Sequence[float], sl: tuple[float, float, int]
) -> Result[SettleResult, SettleError]:
    """Assemble the settled verdict for a run starting at `first`, confirmed at `confirmed`."""
    m = _measured(*sl)
    if isinstance(m, Err):
        return Err(m.danger_err)
    _log.info("settled at index %d (t=%g), confirmed at %d", first, times[first], confirmed)
    return Ok(
        SettleResult(
            settled=True,
            settled_index=first,
            settled_time=times[first],
            confirmed_index=confirmed,
            slope=m.danger_ok,
            window_points=sl[2],
        )
    )
