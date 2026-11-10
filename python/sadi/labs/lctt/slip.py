"""LCTT slip detector: step-like strain jumps at constant load, told apart from log-time creep."""

# frob:ticket 01M6W7R257EXZX1RD7VT3M5GJG

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import median

from pydantic import BaseModel, Field
from typani import Err, ErrorSet, Ok, Result, propagate

from sadi.logging_setup import get_logger

_log = get_logger(__name__)


class SlipError(ErrorSet):
    """Malformed or too-short input to the slip detector; the description says what to fix."""

    LengthMismatch = "times, strain and load must have equal length; pass one value per timestamp"
    NonFinite = "Samples must be finite; drop or repair NaN/inf readings before detecting"
    NonMonotonicTime = "Timestamps must be strictly increasing; check the acquisition clock"
    BeforeLoad = "All samples must be after the load change; trim samples at or before t_load"
    TooShort = "Too few samples for the window; need at least 2*window + 1 samples"


class SlipConfig(BaseModel):
    """Frozen detector parameters: window, threshold multiple k, minimum size, load tolerance."""

    model_config = {"frozen": True}

    window: int = Field(default=3, ge=2, le=10000, description="Neighbour diffs each side")
    k: float = Field(default=5.0, gt=0, le=100, description="Jump must exceed k * its noise sigma")
    min_size: float = Field(default=0.0, ge=0, description="Smallest |step| (strain) to report")
    noise_floor: float = Field(default=1e-12, gt=0, description="Lower bound on noise sigma")
    load_tol: float = Field(default=0.0, ge=0, description="Load change above this is not slip")


def noise_floor_for_lsb(
    full_scale_v: float, strain_per_volt: float, *, bits: int = 16
) -> Result[float, str]:
    """Strain equivalent of one ADC LSB (bipolar +-full_scale_v): the physical noise floor."""
    if not (math.isfinite(full_scale_v) and full_scale_v > 0):
        return Err("full_scale_v must be finite and positive")
    if not (math.isfinite(strain_per_volt) and strain_per_volt != 0):
        return Err("strain_per_volt must be finite and non-zero")
    if bits < 1:
        return Err("bits must be >= 1")
    floor = abs(strain_per_volt) * 2 * full_scale_v / 2**bits
    _log.debug("noise floor for one LSB: %.6g strain", floor)
    return Ok(floor)


@propagate
def slip_config_from_adc(
    full_scale_v: float, strain_per_volt: float, *, bits: int = 16, **overrides: float
) -> Result[SlipConfig, str]:
    """SlipConfig whose noise_floor is one ADC LSB in strain; callers must use this, not 1e-12."""
    floor = noise_floor_for_lsb(full_scale_v, strain_per_volt, bits=bits)
    return Ok(SlipConfig(noise_floor=floor.unwrap(), **overrides))


class SlipEvent(BaseModel):
    """One detected slip: time of the first post-step sample, size (strain) and confidence 0..1."""

    model_config = {"frozen": True}

    time: float
    index: int
    size: float
    z: float
    confidence: float


class SlipReport(BaseModel):
    """Detector output: noise sigma, common log-time creep slope and the slip events."""

    model_config = {"frozen": True}

    sigma: float
    creep_slope: float
    events: tuple[SlipEvent, ...]


def _validate(
    times: Sequence[float], strain: Sequence[float], load: Sequence[float] | None, t_load: float
) -> SlipError | None:
    """Return the first input problem found, or None."""
    n = len(times)
    if len(strain) != n or (load is not None and len(load) != n):
        return SlipError.LengthMismatch
    vals = (*times, *strain, t_load, *(load or ()))
    if not all(math.isfinite(v) for v in vals):
        return SlipError.NonFinite
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        return SlipError.NonMonotonicTime
    if times and times[0] <= t_load:
        return SlipError.BeforeLoad
    return None


def _hampel_residuals(strain: Sequence[float], half: int) -> list[float]:
    """Each first difference minus the median of its neighbours (smooth creep cancels out)."""
    d = [b - a for a, b in zip(strain, strain[1:], strict=False)]
    out: list[float] = []
    for i, v in enumerate(d):
        near = d[max(0, i - half) : i] + d[i + 1 : i + 1 + half]
        out.append(v - median(near))
    return out


def _noise_sigma(resid: Sequence[float], floor: float) -> float:
    """Robust sigma of the residual differences (MAD, insensitive to a few steps)."""
    m = median(resid)
    return max(median(abs(v - m) for v in resid) / 0.6745, floor)


def _pooled_slope(x: Sequence[float], y: Sequence[float], cuts: Sequence[int]) -> float:
    """Common OLS slope of y on x with a separate intercept per segment between cuts."""
    bounds = [0, *cuts, len(x)]
    sxx = sxy = 0.0
    for lo, hi in zip(bounds, bounds[1:], strict=False):
        if hi - lo < 2:
            continue
        xm = sum(x[lo:hi]) / (hi - lo)
        ym = sum(y[lo:hi]) / (hi - lo)
        sxx += sum((v - xm) ** 2 for v in x[lo:hi])
        sxy += sum((v - xm) * (u - ym) for v, u in zip(x[lo:hi], y[lo:hi], strict=True))
    return sxy / sxx if sxx > 0 else 0.0


def detect_slip(
    times: Sequence[float],
    strain: Sequence[float],
    t_load: float,
    load: Sequence[float] | None = None,
    config: SlipConfig | None = None,
) -> Result[SlipReport, SlipError]:
    """Find slip steps (jumps beyond k*noise not explained by log-time creep) in one hold."""
    cfg = config or SlipConfig()
    bad = _validate(times, strain, load, t_load)
    if bad is not None:
        _log.error("slip input rejected: %s", bad.name)
        return Err(bad)
    w, n = cfg.window, len(times)
    if n < 2 * w + 1:
        _log.warning("slip hold too short: %d < %d samples", n, 2 * w + 1)
        return Err(SlipError.TooShort)

    x = [math.log(t - t_load) for t in times]
    resid = _hampel_residuals(strain, w)
    sigma_d = _noise_sigma(resid, cfg.noise_floor)
    events: list[SlipEvent] = []
    for j, size in enumerate(resid):
        i = j + 1  # first sample after the jump
        if j < w:
            # Start guard: onset creep is steepest and one-sided neighbours cannot cancel it.
            _log.debug("jump at i=%d inside start guard; not evaluated", i)
            continue
        z = abs(size) / sigma_d
        if z <= cfg.k:
            continue
        if load is not None and abs(load[i] - load[j]) > cfg.load_tol:
            _log.info("jump at i=%d coincides with a load change; not slip", i)
            continue
        if abs(size) < cfg.min_size:
            _log.info("jump at i=%d below min_size: size=%g", i, size)
            continue
        conf = math.erf(z / math.sqrt(2.0))
        _log.info("slip at t=%g size=%g z=%.2f conf=%.4f", times[i], size, z, conf)
        events.append(SlipEvent(time=times[i], index=i, size=size, z=z, confidence=conf))
    slope = _pooled_slope(x, strain, [e.index for e in events])
    sigma = sigma_d / math.sqrt(2.0)
    _log.debug("slip sigma=%g slope=%g events=%d", sigma, slope, len(events))
    return Ok(SlipReport(sigma=sigma, creep_slope=slope, events=tuple(events)))
