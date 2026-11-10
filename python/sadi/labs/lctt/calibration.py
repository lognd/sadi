"""LCTT LVDT calibration: LINEST-equivalent volts->height fit with standard errors and t95."""

# frob:ticket 01M6W7R28HX7237GMXSNQKWT3Y

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty import (
    Measured,
    MonteCarloError,
    NumericError,
    Provenance,
    UncertainError,
    UncertaintyError,
    t95,
    uncertain,
)

_log = get_logger(__name__)

EvalError = UncertainError | UncertaintyError | NumericError | MonteCarloError
"""Every error an `@uncertain` evaluation can return."""

MIN_POINTS = 3
_MAX_ITER = 100
_TOL = 1e-13
_RANK_TOL = 1e-12
_VOLT_UNIT = "V"
_SLOPE_UNIT = "m/V"
_HEIGHT_UNIT = "m"


class CalibrationError(ErrorSet):
    """Calibration fit failure; the description says what to fix."""

    TooFewPoints = "Need at least 3 calibration points (LINEST needs dof >= 1); capture more"
    LengthMismatch = "volts and heights (and any uncertainty lists) must have equal length"
    NonFinite = "Calibration samples must be finite; remove NaN/inf points"
    DegenerateX = (
        "All calibration voltages are equal, so no height-to-volts line can be fitted. "
        "On hardware, move the LVDT core to a different gauge block before each capture. "
        "The simulator does not move the LVDT: press Skip this step instead"
    )  # frob:ticket 01M72YAG11208WNCXQJ5V612KT
    RankDeficient = "Fit matrix is rank deficient (too few distinct weighted points); recapture"
    BadUncertainty = "Uncertainties must be finite and positive; fix or drop the entries"
    MissingVoltUnc = "errors_in_both needs u_volts; pass voltage uncertainties or disable it"
    NotRepresentable = "Fit result could not be built as Measured; check the calibration data"


class CalibrationBand(BaseModel):
    """Confidence band at the requested voltages: fitted height and the 95% half-width."""

    model_config = {"frozen": True}

    volts: tuple[float, ...]
    height: tuple[float, ...]
    half_width: tuple[float, ...]


class CalibrationFit(BaseModel):
    """LINEST-equivalent fit: slope, intercept (the offset, Q6), covariance, r^2, dof, t95."""

    model_config = {"frozen": True}

    slope: Measured
    intercept: Measured
    se_slope: float
    se_intercept: float
    cov_slope_intercept: float
    se_regression: float
    r2: float
    dof: int
    n: int
    t95: float
    u95_slope: float
    u95_intercept: float
    residuals: tuple[float, ...]
    errors_in_both: bool = False

    @property
    def offset(self) -> Measured:
        """Intercept as the absolute height offset; only the slope feeds strain (Q6)."""
        return self.intercept

    def ci_band(self, volts: Sequence[float], *, prediction: bool = False) -> CalibrationBand:
        """Return the 95% band of the mean height (or a new observation) at `volts`."""
        v = np.asarray(list(volts), dtype=float)
        var = self.se_intercept**2 + 2.0 * v * self.cov_slope_intercept + v**2 * self.se_slope**2
        if prediction:
            var = var + self.se_regression**2
        half = self.t95 * np.sqrt(np.maximum(var, 0.0))
        height = self.slope.value * v + self.intercept.value
        _log.debug("ci_band: %d points prediction=%s", v.size, prediction)
        return CalibrationBand(
            volts=tuple(float(a) for a in v),
            height=tuple(float(a) for a in height),
            half_width=tuple(float(a) for a in half),
        )

    def height_at(self, volts: Measured) -> Result[Measured, EvalError]:
        """Height for a voltage Measured, with the slope/intercept covariance propagated."""
        return height_at(self.slope, self.intercept, volts)

    def displacement(self, delta_volts: Measured) -> Result[Measured, EvalError]:
        """Length change for a voltage change Measured; uses the slope only (Q6)."""
        return displacement(self.slope, delta_volts)


@uncertain
def height_at(slope, intercept, volts):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
    """Calibrated height = slope * volts + intercept (traced; slope/intercept covariance used)."""
    return slope * volts + intercept


@uncertain
def displacement(slope, delta_volts):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
    """Length change = slope * delta volts; the intercept cancels (Q6)."""
    return slope * delta_volts


def _per_point(
    u: float | Sequence[float] | None, n: int
) -> Result[np.ndarray | None, CalibrationError]:
    """Expand a scalar or per-point uncertainty to an array; None stays None."""
    if u is None:
        return Ok(None)
    arr = np.full(n, float(u)) if isinstance(u, int | float) else np.asarray(list(u), dtype=float)
    if arr.shape != (n,):
        return Err(CalibrationError.LengthMismatch)
    if not (np.all(np.isfinite(arr)) and np.all(arr >= 0)):
        return Err(CalibrationError.BadUncertainty)
    return Ok(arr)


def _solve(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> Result[np.ndarray, CalibrationError]:
    """Weighted least squares for (slope, intercept); RankDeficient when singular."""
    design = np.column_stack([x, np.ones_like(x)])
    sw = np.sqrt(w)[:, None]
    weighted = design * sw
    if np.linalg.matrix_rank(weighted, tol=_RANK_TOL * np.linalg.norm(weighted, 2)) < 2:
        return Err(CalibrationError.RankDeficient)
    beta, *_ = np.linalg.lstsq(weighted, y * sw[:, 0], rcond=None)
    return Ok(beta)


def _weights(
    x: np.ndarray,
    y: np.ndarray,
    u_y: np.ndarray | None,
    u_x: np.ndarray | None,
    both: bool,
) -> Result[tuple[np.ndarray, np.ndarray], CalibrationError]:
    """Solve for beta and weights; effective-variance iteration when voltage errors count."""
    n = x.size
    if u_y is None and not (both and u_x is not None):
        return _solve(x, y, np.ones(n)).map(lambda b: (b, np.ones(n)))
    uy2 = np.zeros(n) if u_y is None else u_y**2
    ux2 = np.zeros(n) if (u_x is None or not both) else u_x**2
    w = np.ones(n)
    beta = np.zeros(2)
    slope = 0.0
    for it in range(_MAX_ITER):
        var = uy2 + slope**2 * ux2
        if not np.all(var > 0):
            return Err(CalibrationError.BadUncertainty)
        w = 1.0 / var
        solved = _solve(x, y, w)
        if isinstance(solved, Err):
            return Err(solved.danger_err)
        beta = solved.danger_ok
        done = abs(beta[0] - slope) <= _TOL * max(1.0, abs(beta[0]))
        slope = float(beta[0])
        if done or not ux2.any():
            _log.debug("calibration weights settled after %d iterations", it + 1)
            break
    return Ok((beta, w))


def _measured(
    value: float, se: float, unit: str, dof: float, name: str
) -> Result[Measured, CalibrationError]:
    """Wrap a fitted quantity as Measured with the fit's dof and provenance."""
    m = Measured.create(
        value, se, unit, dof=dof, provenance=Provenance(source="lctt.calibration", derivation=name)
    )
    if isinstance(m, Err):
        _log.error("calibration %s not representable: %s", name, m.danger_err.name)
        return Err(CalibrationError.NotRepresentable)
    return Ok(m.danger_ok)


def fit_calibration(
    volts: Sequence[float],
    heights: Sequence[float],
    u_volts: float | Sequence[float] | None = None,
    u_heights: float | Sequence[float] | None = None,
    *,
    errors_in_both: bool = False,
) -> Result[CalibrationFit, CalibrationError]:
    """Fit height = slope*volts + intercept like LINEST(L, V, TRUE, TRUE), optionally weighted.

    Without uncertainties this is ordinary least squares. With `u_heights` the points are
    weighted by 1/u^2; with `errors_in_both` too, by 1/(u_h^2 + slope^2 u_v^2) (effective
    variance, iterated). Standard errors are scaled by the weighted residuals as LINEST does.
    """
    n = len(volts)
    if len(heights) != n:
        return Err(CalibrationError.LengthMismatch)
    if n < MIN_POINTS:
        _log.warning("calibration needs %d points, got %d", MIN_POINTS, n)
        return Err(CalibrationError.TooFewPoints)
    x = np.asarray(list(volts), dtype=float)
    y = np.asarray(list(heights), dtype=float)
    if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
        return Err(CalibrationError.NonFinite)
    if errors_in_both and u_volts is None:
        return Err(CalibrationError.MissingVoltUnc)
    if u_volts is not None and not errors_in_both:
        _log.warning("u_volts ignored: errors_in_both is off")
    ux = _per_point(u_volts, n)
    uy = _per_point(u_heights, n)
    for res in (ux, uy):
        if isinstance(res, Err):
            _log.error("calibration uncertainty rejected: %s", res.danger_err.name)
            return Err(res.danger_err)
    if np.ptp(x) == 0.0:
        _log.error("calibration voltages are all equal")
        return Err(CalibrationError.DegenerateX)

    solved = _weights(x, y, uy.danger_ok, ux.danger_ok, errors_in_both)
    if isinstance(solved, Err):
        _log.error("calibration solve failed: %s", solved.danger_err.name)
        return Err(solved.danger_err)
    beta, w = solved.danger_ok
    slope, intercept = float(beta[0]), float(beta[1])
    resid = y - (slope * x + intercept)
    dof = n - 2
    ssw = float(np.sum(w * resid**2))
    s2 = ssw / dof
    design = np.column_stack([x, np.ones(n)])
    cov = s2 * np.linalg.inv(design.T @ (design * w[:, None]))
    ybar = float(np.sum(w * y) / np.sum(w))
    sst = float(np.sum(w * (y - ybar) ** 2))
    r2 = 1.0 - ssw / sst if sst > 0 else 1.0
    se_m, se_b = math.sqrt(max(cov[0, 0], 0.0)), math.sqrt(max(cov[1, 1], 0.0))
    k = t95(dof)
    if isinstance(k, Err):
        return Err(CalibrationError.NotRepresentable)
    m = _measured(slope, se_m, _SLOPE_UNIT, dof, "slope")
    b = _measured(intercept, se_b, _HEIGHT_UNIT, dof, "intercept")
    for part in (m, b):
        if isinstance(part, Err):
            return Err(part.danger_err)
    slope_m, icpt_m = m.danger_ok, b.danger_ok
    if se_m > 0 and se_b > 0:
        rho = float(np.clip(cov[0, 1] / (se_m * se_b), -1.0, 1.0))
        slope_m.correlate(icpt_m, rho)
    _log.info(
        "calibration n=%d slope=%g +/- %g intercept=%g r2=%.7f both=%s",
        n,
        slope,
        se_m,
        intercept,
        r2,
        errors_in_both,
    )
    return Ok(
        CalibrationFit(
            slope=slope_m,
            intercept=icpt_m,
            se_slope=se_m,
            se_intercept=se_b,
            cov_slope_intercept=float(cov[0, 1]),
            se_regression=math.sqrt(s2),
            r2=r2,
            dof=dof,
            n=n,
            t95=k.danger_ok,
            u95_slope=k.danger_ok * se_m,
            u95_intercept=k.danger_ok * se_b,
            residuals=tuple(float(r) for r in resid),
            errors_in_both=errors_in_both,
        )
    )
