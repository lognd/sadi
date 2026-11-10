"""Planner calibration: derive volts = slope*height + offset from entered points (or an explicit override)."""

# frob:ticket 01M7301MDWNXK9Z0D8TBDBNP4G

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from typani import Err, Ok, Result

from sadi.labs.lctt.calibration import fit_calibration
from sadi.logging_setup import get_logger

__all__ = ["Calibration", "parse_cal_points", "resolve_calibration"]

_log = get_logger(__name__)

_MAX_REWEIGHT = 50


class Calibration(BaseModel):
    """LVDT calibration volts = slope*height + offset with uncertainty; source says where it came from."""

    model_config = ConfigDict(frozen=True)

    slope_v_per_m: float
    offset_v: float
    se_slope: float = 0.0
    se_offset: float = 0.0
    cov: float = 0.0
    r2: float | None = None
    n: int | None = None
    source: Literal["fit", "override"]

    def summary(self) -> str:
        """One-line operator-facing description, labelling an override as such."""
        if self.source == "override":
            return (
                f"calibration: OVERRIDE (typed, not fitted) slope={self.slope_v_per_m:g} V/m "
                f"offset={self.offset_v:g} V; no uncertainty"
            )
        return (
            f"calibration: fitted slope={self.slope_v_per_m:.6g} +/- {self.se_slope:.3g} V/m "
            f"intercept={self.offset_v:.6g} +/- {self.se_offset:.3g} V r2={self.r2:.6f} n={self.n}"
        )


#: (height m, volts, optional height uncertainty m)
CalPoint = tuple[float, float, float | None]


def parse_cal_points(text: str) -> Result[list[CalPoint], str]:
    """Parse 'height_m:volts[:u_height_m],...' into (height, volts, u_height or None) triples."""
    out: list[CalPoint] = []
    for part in filter(None, (t.strip() for t in text.replace(";", ",").replace("\n", ",").split(","))):
        try:
            fields = part.split(":")
            if len(fields) not in (2, 3):
                raise ValueError("expected 2 or 3 fields")
            u = float(fields[2]) if len(fields) == 3 and fields[2].strip() else None
            out.append((float(fields[0]), float(fields[1]), u))
        except ValueError as exc:
            _log.warning("bad calibration point %r: %s", part, exc)
            return Err(f"Could not read calibration point {part!r} (use height_m:volts or height_m:volts:u_height_m): {exc}")
    return Ok(out)


def _fit(points: list[CalPoint]) -> Result[Calibration, str]:
    """Fit volts against height (weighted by height uncertainty when every point has one).

    Errors, never defaults, on degenerate data; without per-point uncertainties it is unweighted OLS.
    """
    if len({h for h, _, _ in points}) < 2:
        _log.error("calibration needs >= 2 distinct heights, got %d points", len(points))
        return Err("Calibration needs at least 2 distinct heights (height m / volts rows); no default is assumed")
    # lctt fit is generic y = slope*x + intercept: x = height, y = volts here.
    us = [u for _, _, u in points]
    weighted = all(u is not None for u in us)
    if not weighted and any(u is not None for u in us):
        _log.warning("height uncertainty given for only some points; fitting unweighted")
    xs, ys = [h for h, _, _ in points], [v for _, v, _ in points]
    res = fit_calibration(xs, ys)
    if weighted and not isinstance(res, Err):
        # Effective variance: a height error u_h acts as |slope|*u_h on volts; re-weight until settled.
        for _ in range(_MAX_REWEIGHT):
            slope = res.value.slope.value
            res = fit_calibration(xs, ys, u_heights=[abs(slope) * float(u) for u in us if u is not None])
            if isinstance(res, Err) or abs(res.value.slope.value - slope) <= 1e-12 * max(1.0, abs(slope)):
                break
    if isinstance(res, Err):
        _log.error("calibration fit failed: %s", res.error.name)
        return Err(f"Calibration fit failed: {res.error.value}")
    f = res.value
    return Ok(
        Calibration(
            slope_v_per_m=f.slope.value, offset_v=f.intercept.value, se_slope=f.se_slope,
            se_offset=f.se_intercept, cov=f.cov_slope_intercept, r2=f.r2, n=f.n, source="fit",
        )
    )


def resolve_calibration(
    cal_points: str, cal_slope: float | None, cal_offset: float = 0.0
) -> Result[Calibration, str]:
    """Fit from points, or use the explicit slope override; both or neither is an error."""
    has_points = bool(cal_points.strip())
    if has_points and cal_slope is not None:
        return Err("Give calibration points OR an explicit slope override, not both")
    if cal_slope is not None:
        _log.warning("using typed slope override %g V/m (no fit, no uncertainty)", cal_slope)
        try:
            return Ok(Calibration(slope_v_per_m=cal_slope, offset_v=cal_offset, source="override"))
        except ValidationError as exc:  # pragma: no cover - floats always validate
            return Err(str(exc))
    if not has_points:
        return Err("Enter calibration points (height m / volts) to fit the LVDT calibration; nothing is assumed")
    pts = parse_cal_points(cal_points)
    if isinstance(pts, Err):
        return pts
    return _fit(pts.value)
