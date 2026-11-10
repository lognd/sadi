"""Tests for the LCTT calibration fit against the LINEST reference and property checks."""

# frob:ticket 01M6W7R28HX7237GMXSNQKWT3Y

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy import stats
from typani import Err, Ok

from sadi.labs.lctt.calibration import CalibrationError, CalibrationFit, fit_calibration
from sadi.uncertainty import Measured

# 12-point local calibration set; LINEST reference values from the same set
CAL_V = [
    -1.099891e0, 4.720703e0, 5.341562e-1, -4.327925e0, 2.937594e0, -1.976520e0,
    4.553981e0, -3.008625e-1, 1.265852e0, -3.615362e0, 2.882964e0, -1.973938e0,
]  # fmt: skip
CAL_L = [
    2.253400e-2, 3.471500e-2, 2.592300e-2, 1.557000e-2, 3.094300e-2, 2.059000e-2,
    3.433200e-2, 2.397900e-2, 2.742500e-2, 1.707200e-2, 3.081400e-2, 2.046100e-2,
]  # fmt: skip


def _fit(
    v: Sequence[float],
    h: Sequence[float],
    u_volts: float | Sequence[float] | None = None,
    u_heights: float | Sequence[float] | None = None,
    *,
    errors_in_both: bool = False,
) -> CalibrationFit:
    res = fit_calibration(v, h, u_volts, u_heights, errors_in_both=errors_in_both)
    assert isinstance(res, Ok)
    return res.danger_ok


def _err(
    v: Sequence[float],
    h: Sequence[float],
    u_volts: float | Sequence[float] | None = None,
    u_heights: float | Sequence[float] | None = None,
    *,
    errors_in_both: bool = False,
) -> CalibrationError:
    res = fit_calibration(v, h, u_volts, u_heights, errors_in_both=errors_in_both)
    assert isinstance(res, Err)
    return res.danger_err


def _hand_linest(x: list[float], y: list[float]) -> dict[str, float]:
    """Hand-computed LINEST from the domain.md section 3.3 formulas (independent of numpy fit)."""
    n = len(x)
    xb, yb = sum(x) / n, sum(y) / n
    sxx = sum((a - xb) ** 2 for a in x)
    sxy = sum((a - xb) * (b - yb) for a, b in zip(x, y, strict=True))
    m = sxy / sxx
    b0 = yb - m * xb
    ssres = sum((c - (m * a + b0)) ** 2 for a, c in zip(x, y, strict=True))
    sstot = sum((c - yb) ** 2 for c in y)
    sel = math.sqrt(ssres / (n - 2))
    return {
        "slope": m,
        "intercept": b0,
        "se_slope": sel / math.sqrt(sxx),
        "se_intercept": sel * math.sqrt(1 / n + xb**2 / sxx),
        "r2": 1 - ssres / sstot,
        "se_l": sel,
        "t95": float(stats.t.ppf(0.975, n - 2)),
    }


# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
def test_matches_hand_linest_reference() -> None:
    f = _fit(CAL_V, CAL_L)
    ref = _hand_linest(CAL_V, CAL_L)
    assert f.slope.value == pytest.approx(ref["slope"], rel=1e-10)
    assert f.intercept.value == pytest.approx(ref["intercept"], rel=1e-10)
    assert f.se_slope == pytest.approx(ref["se_slope"], rel=1e-9)
    assert f.se_intercept == pytest.approx(ref["se_intercept"], rel=1e-9)
    assert f.r2 == pytest.approx(ref["r2"], rel=1e-10)
    assert f.se_regression == pytest.approx(ref["se_l"], rel=1e-9)
    assert f.t95 == pytest.approx(ref["t95"], rel=1e-12)
    assert f.dof == 10
    assert f.n == 12
    assert f.u95_slope == pytest.approx(ref["t95"] * ref["se_slope"], rel=1e-9)
    assert sum(f.residuals) == pytest.approx(0.0, abs=1e-12)


# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
def test_matches_reference_vi_oracle() -> None:
    f = _fit(CAL_V, CAL_L)
    assert f.slope.value == pytest.approx(2.114583e-3, rel=1e-6)
    assert f.intercept.value == pytest.approx(2.472866e-2, rel=1e-6)
    assert f.se_slope == pytest.approx(6.734580e-6, rel=1e-5)  # file values rounded: 1e-5
    assert f.se_intercept == pytest.approx(1.970728e-5, rel=1e-5)
    assert f.r2 == pytest.approx(9.998986e-1, rel=1e-6)
    assert f.se_regression == pytest.approx(6.790817e-5, rel=1e-5)
    assert f.t95 == pytest.approx(2.228139, rel=1e-6)
    assert f.u95_slope == pytest.approx(1.500558e-5, rel=1e-5)


# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
def test_measured_carries_dof_and_covariance() -> None:
    f = _fit(CAL_V, CAL_L)
    assert f.slope.dof == 10
    assert f.slope.std_unc == pytest.approx(f.se_slope)
    rho = f.slope.covariance_with(f.intercept) / (f.se_slope * f.se_intercept)
    assert rho == pytest.approx(f.cov_slope_intercept / (f.se_slope * f.se_intercept), rel=1e-9)
    assert -1.0 <= rho <= 1.0


# frob:tests python/sadi/labs/lctt/calibration.py::CalibrationFit.ci_band
def test_ci_band_matches_hand_formula() -> None:
    f = _fit(CAL_V, CAL_L)
    xb = sum(CAL_V) / 12
    sxx = sum((a - xb) ** 2 for a in CAL_V)
    ref = _hand_linest(CAL_V, CAL_L)
    xs = [-4.0, xb, 4.5]
    band = f.ci_band(xs)
    for v, h, hw in zip(xs, band.height, band.half_width, strict=True):
        assert h == pytest.approx(ref["slope"] * v + ref["intercept"], rel=1e-10)
        want = ref["t95"] * ref["se_l"] * math.sqrt(1 / 12 + (v - xb) ** 2 / sxx)
        assert hw == pytest.approx(want, rel=1e-9)
    pred = f.ci_band(xs, prediction=True)
    assert all(p > c for p, c in zip(pred.half_width, band.half_width, strict=True))
    assert band.half_width[1] == min(band.half_width)


# frob:tests python/sadi/labs/lctt/calibration.py::height_at
# frob:tests python/sadi/labs/lctt/calibration.py::CalibrationFit.height_at
def test_height_at_uses_slope_intercept_covariance() -> None:
    f = _fit(CAL_V, CAL_L)
    reg_v = Measured.create(2.0, 0.0, "V").unwrap()
    out = f.height_at(reg_v).unwrap()
    assert out.value == pytest.approx(f.slope.value * 2.0 + f.intercept.value)
    var = f.se_intercept**2 + 4.0 * f.cov_slope_intercept + 4.0 * f.se_slope**2
    assert out.std_unc == pytest.approx(math.sqrt(var), rel=1e-6)


# frob:tests python/sadi/labs/lctt/calibration.py::displacement
# frob:tests python/sadi/labs/lctt/calibration.py::CalibrationFit.displacement
def test_displacement_uses_slope_only() -> None:
    f = _fit(CAL_V, CAL_L)
    dv = Measured.create(-1.5, 0.0, "V").unwrap()
    out = f.displacement(dv).unwrap()
    assert out.value == pytest.approx(f.slope.value * -1.5)
    assert out.std_unc == pytest.approx(abs(1.5) * f.se_slope, rel=1e-6)


# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
def test_typed_errors() -> None:
    assert _err([1.0, 2.0], [1.0, 2.0]) is CalibrationError.TooFewPoints
    assert _err([1.0, 2.0, 3.0], [1.0, 2.0]) is CalibrationError.LengthMismatch
    assert _err([1.0, 2.0, math.nan], [1.0, 2.0, 3.0]) is CalibrationError.NonFinite
    assert _err([2.0, 2.0, 2.0], [1.0, 2.0, 3.0]) is CalibrationError.DegenerateX
    assert _err([1, 2, 3], [1, 2, 3], u_heights=[1, -1, 1]) is CalibrationError.BadUncertainty
    assert _err([1, 2, 3], [1, 2, 3], errors_in_both=True) is CalibrationError.MissingVoltUnc
    assert _err([1, 2, 3], [1, 2, 3], u_heights=[0, 1, 1]) is CalibrationError.BadUncertainty


# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
def test_rank_deficient_when_one_point_carries_all_weight() -> None:
    # two huge-weight-ratio points leave a single effective point; matrix is numerically rank 1
    res = fit_calibration([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], u_heights=[1e-100, 1.0, 1.0])
    assert isinstance(res, Err)
    assert res.danger_err is CalibrationError.RankDeficient


# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
def test_uniform_height_uncertainty_equals_unweighted() -> None:
    plain = _fit(CAL_V, CAL_L)
    weighted = _fit(CAL_V, CAL_L, u_heights=1e-4)
    assert weighted.slope.value == pytest.approx(plain.slope.value, rel=1e-10)
    assert weighted.se_slope == pytest.approx(plain.se_slope, rel=1e-9)
    assert weighted.r2 == pytest.approx(plain.r2, rel=1e-10)


# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
def test_errors_in_both_matches_effective_variance_fixed_point() -> None:
    ux = [0.01 * (1 + i % 3) for i in range(12)]
    uy = [5e-5 * (1 + i % 2) for i in range(12)]
    f = _fit(CAL_V, CAL_L, u_volts=ux, u_heights=uy, errors_in_both=True)
    m, b = f.slope.value, f.intercept.value
    w = 1.0 / (np.array(uy) ** 2 + m**2 * np.array(ux) ** 2)
    x, y = np.array(CAL_V), np.array(CAL_L)
    xw, yw = np.sum(w * x) / w.sum(), np.sum(w * y) / w.sum()
    m_ref = np.sum(w * (x - xw) * (y - yw)) / np.sum(w * (x - xw) ** 2)
    assert m == pytest.approx(m_ref, rel=1e-9)
    assert b == pytest.approx(yw - m_ref * xw, rel=1e-9)
    assert f.errors_in_both


# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
def test_voltage_uncertainty_ignored_without_flag() -> None:
    a = _fit(CAL_V, CAL_L, u_heights=1e-4)
    b = _fit(CAL_V, CAL_L, u_volts=0.5, u_heights=1e-4)
    assert a.slope.value == b.slope.value


_TAIL_P = 1e-9  # two-sided miss probability per check (negligible over all examples)

_X = st.lists(
    st.floats(-5, 5, allow_nan=False), min_size=6, max_size=30, unique_by=lambda v: round(v, 3)
)


# frob:ticket 01M6WF38QK5F60GK3RVQT3RGZY
# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
# Root cause of the flake: the estimated SE has only n-2 (>=4) dof, so the error
# is Student-t, not normal; "6 sigma" fails ~0.4% per check at n=6 (~40% per run
# over 60 examples x 2 checks). Bound with the t quantile instead, and derandomize.
@settings(max_examples=60, deadline=None, derandomize=True)
@given(
    xs=_X,
    slope=st.floats(1e-3, 5e-3),
    icpt=st.floats(0.01, 0.04),
    seed=st.integers(0, 2**31),
)
def test_property_slope_recovered_within_standard_error(
    xs: list[float], slope: float, icpt: float, seed: int
) -> None:
    rng = np.random.default_rng(seed)
    sigma = 5e-5
    ys = [slope * x + icpt + rng.normal(0, sigma) for x in xs]
    if np.ptp(xs) < 2.0:
        return
    f = _fit(xs, ys)
    tcrit = float(stats.t.isf(_TAIL_P / 2, len(xs) - 2))
    assert abs(f.slope.value - slope) < tcrit * f.se_slope + 1e-12
    assert abs(f.intercept.value - icpt) < tcrit * f.se_intercept + 1e-12
    ref = _hand_linest(xs, ys)
    assert f.se_slope == pytest.approx(ref["se_slope"], rel=1e-6)


# frob:ticket 01M6WF38QK5F60GK3RVQT3RGZY
# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
# Same flake as above: SE is estimated (finite dof), so bound with the t quantile.
@settings(max_examples=40, deadline=None, derandomize=True)
@given(xs=_X, seed=st.integers(0, 2**31), scale=st.floats(0.5, 5.0))
def test_property_weighted_fit_recovers_slope(xs: list[float], seed: int, scale: float) -> None:
    if np.ptp(xs) < 2.0:
        return
    rng = np.random.default_rng(seed)
    uy = [1e-4 * (1 + scale * abs(x) / 5) for x in xs]
    ys = [2e-3 * x + 0.025 + rng.normal(0, u) for x, u in zip(xs, uy, strict=True)]
    f = _fit(xs, ys, u_heights=uy)
    tcrit = float(stats.t.isf(_TAIL_P / 2, len(xs) - 2))
    assert abs(f.slope.value - 2e-3) < tcrit * f.se_slope + 1e-12
    scaled = _fit(xs, ys, u_heights=[7 * u for u in uy])
    assert scaled.slope.value == pytest.approx(f.slope.value, rel=1e-9)
    assert scaled.se_slope == pytest.approx(f.se_slope, rel=1e-9)


# frob:tests python/sadi/labs/lctt/calibration.py::CalibrationFit.offset
def test_offset_is_the_intercept() -> None:
    f = _fit(CAL_V, CAL_L)
    assert f.offset is f.intercept


# frob:ticket ~5V612KT
# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
def test_degenerate_message_says_what_to_do() -> None:
    """The degenerate-voltage message names the hardware action and the sim Skip."""
    text = CalibrationError.DegenerateX.value
    assert "gauge block" in text
    assert "Skip" in text
