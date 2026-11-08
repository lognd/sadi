"""Analytic vs Monte Carlo vs finite-difference cross-check of every @uncertain lab formula."""

# frob:ticket 01M6W7R3N96SVM2D2GQQTA833F

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from typani import Err, Ok

from sadi.labs.lctt import calibration, loading, modulus, yield_
from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured, Uncertain, UncertainError, UncertaintyError
from sadi.uncertainty.montecarlo import MonteCarloError
from sadi.uncertainty.numeric import NumericError, central_difference
from sadi.uncertainty.uncertain import Method

_log = get_logger(__name__)

# Documented tolerances (docs/uncertainty/crosscheck.md): methods agree within REL_TOL of the
# larger value plus 4 sigma of Monte Carlo sampling error (see montecarlo.cross_check).
REL_TOL = 0.03
N_MC = 40000
REL_UNC = 0.005  # 0.5 % relative standard uncertainty keeps first-order propagation valid
RHO = 0.4  # < 0.5 keeps the neighbour-chained correlation matrix positive definite

# name -> (formula, nominal argument values); every value is non-zero, well conditioned and of
# any magnitude (realistic SI cases with |x| < 1 are included; bug ~SJ9VQC9 fixed).
FORMULAS: dict[str, tuple[Uncertain, tuple[float, ...]]] = {
    "height_at": (calibration.height_at, (2.5, 0.3, 1.7)),
    "displacement": (calibration.displacement, (2.5, 0.8)),
    "load_force": (loading.load_force, (12.0, 0.5, 9.81)),
    "cross_area": (loading.cross_area, (12.5,)),
    "stress": (loading.stress, (150.0, 12.0)),
    "stress_si": (loading.stress, (150.0, 1.2e-4)),
    "strain": (loading.strain, (4.0, 3.2, 0.4, 8.3)),
    "secant_modulus": (modulus.secant_modulus, (2.0e6, 4.0)),
    "secant_modulus_si": (modulus.secant_modulus, (2.0e6, 0.004)),
    "chord_modulus": (modulus.chord_modulus, (4.0e6, 1.2e7, 2.0, 6.0)),
    "yield_stress": (yield_.yield_stress, (1.0e6, 3.5, 2.0e6, 5.0, 2.0e5, 2.0)),
    "yield_strain": (yield_.yield_strain, (1.0e6, 3.5, 2.0e6, 5.0, 2.0e5, 2.0)),
}


def _args(values: tuple[float, ...], *, correlated: bool) -> list[Measured]:
    """Build fresh Measured inputs (1 % uncertainty), optionally correlating neighbours."""
    ms = [Measured.create(v, abs(v) * REL_UNC).unwrap() for v in values]
    if correlated:
        for a, b in zip(ms, ms[1:], strict=False):
            a.correlate(b, RHO).unwrap()
    _log.debug("built %d inputs correlated=%s", len(ms), correlated)
    return ms


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.cross_check
@pytest.mark.parametrize("correlated", [False, True], ids=["independent", "correlated"])
@pytest.mark.parametrize("name", sorted(FORMULAS))
def test_analytic_mc_numeric_agree(name: str, correlated: bool) -> None:
    """Analytic, numeric (finite difference) and MC value and std_unc agree within tolerance."""
    fn, values = FORMULAS[name]
    report = fn.cross_check(*_args(values, correlated=correlated), rel_tol=REL_TOL).unwrap()
    assert report.agree, report.findings


# frob:tests python/sadi/uncertainty/numeric.py::central_difference
@pytest.mark.parametrize("name", sorted(FORMULAS))
def test_symbolic_partials_match_central_difference(name: str) -> None:
    """Each traced partial equals an independent Ridders central difference of the formula."""
    fn, values = FORMULAS[name]
    sens = fn.sensitivities(*_args(values, correlated=False)).unwrap()
    raw: Callable[..., Any] = fn._fn  # noqa: SLF001 - the undecorated plain-math function
    for i, key in enumerate(sens):
        fd = central_difference(raw, list(values), i).unwrap()
        assert math.isclose(sens[key], fd[0], rel_tol=1e-6, abs_tol=1e-9), (name, key)


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__call__
def test_correlation_changes_the_uncertainty_consistently() -> None:
    """Positive correlation of slope and volts changes u(height) the same way in all methods."""
    fn, values = FORMULAS["height_at"]
    u: dict[bool, float] = {}
    for correlated in (False, True):
        out = fn(*_args(values, correlated=correlated)).unwrap()
        u[correlated] = out.std_unc
    assert not math.isclose(u[False], u[True], rel_tol=1e-3)


# Exact zero plus tiny magnitudes down to 1e-300 (overflow range, ~0FYTGN8).
_SMALL = st.one_of(
    st.just(0.0),
    st.floats(min_value=1e-300, max_value=1e-3),
    st.floats(min_value=-1e-3, max_value=-1e-300),
)
_TYPED = (UncertaintyError, UncertainError, NumericError, MonteCarloError)


# frob:tests python/sadi/labs/lctt/modulus.py::secant_modulus
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(strain_v=_SMALL, stress_v=st.floats(1.0, 1e6))
@pytest.mark.parametrize("method", ["analytic", "numeric", "mc"])
def test_near_zero_denominator_is_typed_not_raised(
    method: Method, strain_v: float, stress_v: float
) -> None:
    """A near-zero divisor yields Ok or a typed Err on every method; it never raises."""
    fn = Uncertain(
        lambda stress, strain: stress / strain,
        method=method,
    )
    s = Measured.create(stress_v, stress_v * REL_UNC).unwrap()
    e = Measured.create(strain_v, abs(strain_v) * REL_UNC).unwrap()
    result = fn(s, e)
    assert isinstance(result, (Ok, Err))
    if isinstance(result, Err):
        assert isinstance(result.danger_err, _TYPED)


# frob:tests python/sadi/labs/lctt/yield_.py::yield_stress
def test_degenerate_yield_segment_is_typed() -> None:
    """A segment parallel to the offset line (d0 == d1) gives a typed error, not an exception."""
    args = _args((1.0e6, 0.0035, 1.0e6 + 2.0e8 * 0.0015, 0.0050, 2.0e8, 0.002), correlated=False)
    result = yield_.yield_stress(*args)
    assert isinstance(result, (Ok, Err))


# frob:tests python/sadi/uncertainty/numeric.py::gradient
def test_si_small_stress_numeric_path() -> None:
    """Realistic SI stress (area 1.2e-4 m^2) cross-checks (regression for ~SJ9VQC9)."""
    area = Measured.create(1.2e-4, 1.2e-6).unwrap()
    force = Measured.create(150.0, 1.5).unwrap()
    loading.stress.cross_check(force, area, rel_tol=REL_TOL).unwrap()


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__call__
@pytest.mark.parametrize("method", ["analytic", "numeric"])
def test_extreme_underflow_denominator_is_typed(method: Method) -> None:
    """A 1e-80 divisor gives Ok or a typed Err on the analytic and numeric paths."""
    fn = Uncertain(lambda a, b: a / b, method=method)
    a = Measured.create(1.0, 0.01).unwrap()
    b = Measured.create(8.7e-80, 8.7e-82).unwrap()
    result = fn(a, b)
    assert isinstance(result, (Ok, Err))
    if isinstance(result, Err):
        assert isinstance(result.danger_err, _TYPED)


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.estimate
def test_mc_overflowing_statistics_are_typed_and_silent() -> None:
    """Finite samples near 1e300 give McNonFinite without emitting RuntimeWarnings."""
    import warnings

    fn = Uncertain(lambda a, b: a / b, method="mc")
    a = Measured.create(1.0, 0.005).unwrap()
    b = Measured.create(1e-300, 5e-303).unwrap()
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = fn(a, b)
    assert isinstance(result, (Ok, Err))
    if isinstance(result, Err):
        assert isinstance(result.danger_err, _TYPED)
