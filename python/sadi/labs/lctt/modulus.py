"""LCTT Young's modulus: windowed OLS fit, r^2 gate, per-point secant E and the U4 budget."""

# frob:ticket 01M6W7R3BBDEXG9CPYWTQ7ZKZW

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

import numpy as np
from pydantic import BaseModel, Field
from typani import Err, ErrorSet, Ok, Result

from sadi.labs.lctt.calibration import fit_calibration
from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured, Provenance, uncertain
from sadi.uncertainty.budget import Budget

_log = get_logger(__name__)

E_UNIT = "Pa"
MIN_WINDOW = 3


class ModulusError(ErrorSet):
    """Modulus fit failure; the description says what to fix."""

    BadWindow = "Window must satisfy 0 <= first < last < n with at least 3 points; adjust it"
    Fit = "Linear fit failed on the window; check for repeated strains or non-finite data"
    Propagation = "Uncertainty propagation failed; check units and inputs"
    NoWindow = "No window of enough points reaches the r^2 threshold; lower it or pick by hand"


class SettleSource(StrEnum):
    """What declared a point settled, recorded per fitted point for the report."""

    SETTLED_WINDOW = "settled_window"
    FORCED_EARLY = "forced_early"
    FIXED_DWELL = "fixed_dwell"


class CurvePoint(BaseModel):
    """One captured point: stress and strain Measured plus how it settled and any saturation."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    index: int
    stress: Measured
    strain: Measured
    settle_source: SettleSource = SettleSource.SETTLED_WINDOW
    saturated: bool = False


class ModulusConfig(BaseModel):
    """Frozen fit options: r^2 warning threshold and the auto-window hint minimum size."""

    model_config = {"frozen": True}

    r2_threshold: float = Field(default=0.995, ge=0, le=1, description="Warn below this r^2")
    min_window: int = Field(default=MIN_WINDOW, ge=MIN_WINDOW, description="Auto-window floor")


class ModulusFit(BaseModel):
    """E over a window: E, SE, U95, r^2, n, the window, settle sources, flags and U4 budget."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    modulus: Measured
    std_error: float
    u95: float
    r2: float
    n: int
    first: int
    last: int
    settle_sources: tuple[tuple[int, SettleSource], ...]
    low_r2: bool
    saturated_points: tuple[int, ...] = ()
    budget: Budget | None = None


class SecantPoint(BaseModel):
    """Per-point secant modulus sigma/eps, or None where strain is zero."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    index: int
    modulus: Measured | None


@uncertain
def secant_modulus(stress, strain):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
    """Secant modulus E_s = sigma / eps."""
    return stress / strain


@uncertain
def chord_modulus(s_first, s_last, e_first, e_last):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
    """Window chord modulus (s_last - s_first) / (e_last - e_first), the U4 budget form."""
    return (s_last - s_first) / (e_last - e_first)


def fit_modulus(
    points: Sequence[CurvePoint], first: int, last: int, config: ModulusConfig | None = None
) -> Result[ModulusFit, ModulusError]:
    """Fit E by OLS of stress on strain over points[first..last] inclusive (manual window)."""
    cfg = config or ModulusConfig()
    if not (0 <= first < last < len(points)) or last - first + 1 < MIN_WINDOW:
        _log.warning("fit_modulus: bad window %d..%d of %d", first, last, len(points))
        return Err(ModulusError.BadWindow)
    win = points[first : last + 1]
    fit = fit_calibration([p.strain.value for p in win], [p.stress.value for p in win])
    if isinstance(fit, Err):
        _log.warning("fit_modulus: fit failed: %s", fit.danger_err.name)
        return Err(ModulusError.Fit)
    f = fit.danger_ok
    made = Measured.create(
        f.slope.value,
        f.se_slope,
        E_UNIT,
        dof=f.dof,
        provenance=Provenance(source="lctt.modulus", derivation=f"ols[{first}..{last}]"),
    )
    if isinstance(made, Err):
        return Err(ModulusError.Propagation)
    low = f.r2 < cfg.r2_threshold
    sat = tuple(p.index for p in win if p.saturated)
    if low:
        _log.warning("fit_modulus: r2 %.5f below %.5f", f.r2, cfg.r2_threshold)
    if sat:
        _log.warning("fit_modulus: saturated points in window: %s", sat)
    budget = chord_modulus.budget(win[0].stress, win[-1].stress, win[0].strain, win[-1].strain)
    if isinstance(budget, Err):
        _log.warning("fit_modulus: budget unavailable: %s", budget.danger_err)
    _log.info("fit_modulus: E=%g se=%g r2=%.5f n=%d", f.slope.value, f.se_slope, f.r2, f.n)
    return Ok(
        ModulusFit(
            modulus=made.danger_ok,
            std_error=f.se_slope,
            u95=f.u95_slope,
            r2=f.r2,
            n=f.n,
            first=first,
            last=last,
            settle_sources=tuple((p.index, p.settle_source) for p in win),
            low_r2=low,
            saturated_points=sat,
            budget=None if isinstance(budget, Err) else budget.danger_ok,
        )
    )


def secant_moduli(points: Sequence[CurvePoint]) -> Result[list[SecantPoint], ModulusError]:
    """Secant E at every point; None where strain is zero (undefined)."""
    out: list[SecantPoint] = []
    for p in points:
        if p.strain.value == 0.0:
            out.append(SecantPoint(index=p.index, modulus=None))
            continue
        e = secant_modulus(p.stress, p.strain)
        if isinstance(e, Err):
            _log.warning("secant_moduli: point %d failed: %s", p.index, e.danger_err)
            return Err(ModulusError.Propagation)
        out.append(SecantPoint(index=p.index, modulus=e.danger_ok))
    return Ok(out)


def suggest_window(
    points: Sequence[CurvePoint], config: ModulusConfig | None = None
) -> Result[tuple[int, int], ModulusError]:
    """Hint only: the longest window whose r^2 meets the threshold (earliest wins ties)."""
    cfg = config or ModulusConfig()
    x = np.array([p.strain.value for p in points])
    y = np.array([p.stress.value for p in points])
    best: tuple[int, int] | None = None
    for a in range(len(points)):
        for b in range(len(points) - 1, a + cfg.min_window - 2, -1):
            if best is not None and b - a <= best[1] - best[0]:
                break
            if _r2(x[a : b + 1], y[a : b + 1]) >= cfg.r2_threshold:
                best = (a, b)
                break
    if best is None:
        _log.info("suggest_window: none meets r2 >= %g", cfg.r2_threshold)
        return Err(ModulusError.NoWindow)
    _log.info("suggest_window: %d..%d", *best)
    return Ok(best)


def _r2(x: np.ndarray, y: np.ndarray) -> float:
    """Coefficient of determination of the OLS line (0 when degenerate)."""
    if np.ptp(x) == 0.0:
        return 0.0
    slope, icpt = np.polyfit(x, y, 1)
    sst = float(np.sum((y - y.mean()) ** 2))
    if sst == 0.0:
        return 1.0
    return 1.0 - float(np.sum((y - (slope * x + icpt)) ** 2)) / sst
