"""Tests for the LCTT E fit, secant E, offset yield and saturation flags (synthetic data)."""

# frob:ticket 01M6W7R3BBDEXG9CPYWTQ7ZKZW

from __future__ import annotations

import pytest
from typani import Err

from sadi.labs.lctt.modulus import (
    CurvePoint,
    ModulusConfig,
    ModulusError,
    SettleSource,
    fit_modulus,
    secant_moduli,
    suggest_window,
)
from sadi.labs.lctt.saturation import SaturationConfig, SaturationError, check_saturation
from sadi.labs.lctt.yield_ import YieldError, find_yield
from sadi.uncertainty import Measured

E_TRUE = 70e9


def _m(v: float, u: float, unit: str) -> Measured:
    return Measured.create(v, u, unit).danger_ok


def _curve(n: int = 20, yield_at: int = 8) -> list[CurvePoint]:
    """Linear to point `yield_at`, then flat-ish plastic hardening."""
    pts = []
    for i in range(n):
        eps = 0.0005 * (i + 1)
        sig = (
            E_TRUE * eps
            if i <= yield_at
            else E_TRUE * 0.0005 * (yield_at + 1) + 1e6 * (i - yield_at) ** 2
        )
        src = SettleSource.FORCED_EARLY if i == 3 else SettleSource.SETTLED_WINDOW
        pts.append(
            CurvePoint(
                index=i,
                stress=_m(sig, 1e5, "Pa"),
                strain=_m(eps, 1e-6, "dimensionless"),
                settle_source=src,
            )
        )
    return pts


# frob:tests python/sadi/labs/lctt/modulus.py::fit_modulus
# frob:tests python/sadi/labs/lctt/modulus.py::chord_modulus
def test_fit_recovers_e_with_stats() -> None:
    fit = fit_modulus(_curve(), 0, 7).danger_ok
    assert fit.modulus.value == pytest.approx(E_TRUE, rel=1e-9)
    assert fit.r2 == pytest.approx(1.0)
    assert fit.n == 8
    assert fit.u95 >= 0
    assert not fit.low_r2
    assert (3, SettleSource.FORCED_EARLY) in fit.settle_sources
    assert fit.budget is not None and fit.budget.rows


# frob:tests python/sadi/labs/lctt/modulus.py::fit_modulus
def test_low_r2_flagged_on_plastic_window() -> None:
    fit = fit_modulus(_curve(), 0, 15, ModulusConfig(r2_threshold=0.9999)).danger_ok
    assert fit.low_r2


# frob:tests python/sadi/labs/lctt/modulus.py::fit_modulus
@pytest.mark.parametrize("first,last", [(-1, 4), (4, 4), (0, 1), (0, 99)])
def test_bad_window(first: int, last: int) -> None:
    assert fit_modulus(_curve(), first, last) == Err(ModulusError.BadWindow)


# frob:tests python/sadi/labs/lctt/modulus.py::secant_moduli
# frob:tests python/sadi/labs/lctt/modulus.py::secant_modulus
def test_secant_and_zero_strain() -> None:
    pts = _curve()
    pts.append(
        CurvePoint(index=99, stress=_m(0.0, 1.0, "Pa"), strain=_m(0.0, 1e-6, "dimensionless"))
    )
    sec = secant_moduli(pts).danger_ok
    assert sec[0].modulus is not None
    assert sec[0].modulus.value == pytest.approx(E_TRUE)
    assert sec[-1].modulus is None


# frob:tests python/sadi/labs/lctt/modulus.py::suggest_window
def test_suggest_window_is_a_hint() -> None:
    first, last = suggest_window(_curve(), ModulusConfig(r2_threshold=0.99999)).danger_ok
    assert (first, last) == (0, 8)


# frob:tests python/sadi/labs/lctt/modulus.py::suggest_window
def test_suggest_window_none() -> None:
    zig = [
        CurvePoint(
            index=i,
            stress=_m(1e8 * (i % 2), 1e5, "Pa"),
            strain=_m(0.001 * (i + 1), 1e-6, "dimensionless"),
        )
        for i in range(6)
    ]
    assert suggest_window(zig, ModulusConfig(r2_threshold=0.99)) == Err(ModulusError.NoWindow)


# frob:tests python/sadi/labs/lctt/yield_.py::find_yield
# frob:tests python/sadi/labs/lctt/yield_.py::yield_stress
# frob:tests python/sadi/labs/lctt/yield_.py::yield_strain
def test_offset_yield_matches_closed_form() -> None:
    pts = _curve()
    e = fit_modulus(pts, 0, 7).danger_ok.modulus
    res = find_yield(pts, e).danger_ok
    # offset line sigma = E(eps - 0.002) meets the hardening segment past index 8
    assert res.segment[0] >= 8
    assert res.yield_stress.value == pytest.approx(
        E_TRUE * (res.yield_strain.value - 0.002), rel=1e-9
    )
    assert res.yield_stress.std_unc > 0
    assert res.ultimate_index == 19


# frob:tests python/sadi/labs/lctt/yield_.py::find_yield
def test_no_crossing() -> None:
    pts = _curve(n=6, yield_at=99)
    e = fit_modulus(pts, 0, 5).danger_ok.modulus
    assert find_yield(pts, e) == Err(YieldError.NoCrossing)
    assert find_yield(pts[:1], e) == Err(YieldError.TooFewPoints)


# frob:tests python/sadi/labs/lctt/saturation.py::check_saturation
# frob:tests python/sadi/labs/lctt/saturation.py::SaturationFlag.message
def test_saturation_thresholds() -> None:
    assert check_saturation(0, [1.0, -4.95]).danger_ok.saturated
    ok = check_saturation(1, [4.9, -4.9]).danger_ok
    assert not ok.saturated and ok.message == ""
    cfg = SaturationConfig(threshold_v=4.8)
    flag = check_saturation(2, [4.85], cfg).danger_ok
    assert flag.saturated and "4.85" in flag.message
    assert check_saturation(3, [float("nan")]) == Err(SaturationError.NonFinite)
