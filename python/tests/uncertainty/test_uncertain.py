"""Tests for @uncertain: partials, full-covariance RSS, MC cross-check, typed errors."""

# frob:ticket 01M6W7R1RD3P97HFFDZ2NVD83Y

from __future__ import annotations

import math

import numpy as np
import sympy
import typani
from hypothesis import given, settings
from hypothesis import strategies as st
from typani import Err

import sadi.uncertainty as unc
from sadi.uncertainty import (
    CovarianceRegistry,
    Measured,
    UncertainError,
    UncertaintyError,
    hint,
    uncertain,
)
from sadi.uncertainty.cache import KeyedCache
from sadi.uncertainty.symbolic import TRACE_CACHE, UNIT_CACHE

POS = st.floats(min_value=0.5, max_value=100.0, allow_nan=False, allow_infinity=False)
UNC = st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)


def _mk(reg: CovarianceRegistry, v: float, u: float, unit: str = "m") -> Measured:
    """Create a Measured in registry `reg`."""
    return Measured.create(v, u, unit, registry=reg).unwrap()


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__call__
def test_matches_hand_derived_partials() -> None:
    """f = x*y/z against closed-form RSS for independent inputs."""
    reg = CovarianceRegistry()
    f = uncertain(lambda x, y, z: x * y / z, registry=reg)
    x, y, z = _mk(reg, 3.0, 0.1), _mk(reg, 4.0, 0.2, "s"), _mk(reg, 2.0, 0.05, "kg")
    out = f(x, y, z).unwrap()
    assert math.isclose(out.value, 6.0)
    exp = math.sqrt((4 / 2 * 0.1) ** 2 + (3 / 2 * 0.2) ** 2 + (3 * 4 / 4 * 0.05) ** 2)
    assert math.isclose(out.std_unc, exp, rel_tol=1e-9)
    assert out.unit == "m * s / kg" or "kg" in out.unit


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__call__
def test_correlation_changes_answer() -> None:
    """Slope/intercept style correlation: ignoring it gives a different, wrong result."""
    reg = CovarianceRegistry()
    f = uncertain(lambda a, b: a + b, registry=reg)
    a, b = _mk(reg, 2.0, 0.3), _mk(reg, 1.0, 0.4)
    indep = f(a, b).unwrap().std_unc
    assert math.isclose(indep, 0.5)
    a.correlate(b, -0.8, reg).unwrap()
    corr = f(a, b).unwrap().std_unc
    expected = math.sqrt(0.09 + 0.16 + 2 * -0.8 * 0.3 * 0.4)
    assert math.isclose(corr, expected, rel_tol=1e-9)
    assert not math.isclose(corr, indep, rel_tol=1e-3)


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__call__
def test_monte_carlo_cross_check() -> None:
    """Linearised result matches a Monte Carlo draw from the correlated Gaussian."""
    reg = CovarianceRegistry()
    f = uncertain(lambda a, b: a * sympy.exp(-b), unit="N", registry=reg)
    a, b = _mk(reg, 10.0, 0.1, "N"), _mk(reg, 0.5, 0.02)
    a.correlate(b, 0.6, reg).unwrap()
    out = f(a, b).unwrap()
    cov = [[0.1**2, 0.6 * 0.1 * 0.02], [0.6 * 0.1 * 0.02, 0.02**2]]
    s = np.random.default_rng(1).multivariate_normal([10.0, 0.5], cov, size=200_000)
    mc = (s[:, 0] * np.exp(-s[:, 1])).std()
    assert math.isclose(out.std_unc, mc, rel_tol=0.02)


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.symbolic
# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.partials
# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.latex
# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.sensitivities
def test_exposes_symbolic_partials_latex_sensitivities() -> None:
    """Introspection returns the sympy expression, partials, LaTeX and numeric partials."""
    reg = CovarianceRegistry()

    @uncertain(unit="m**2", registry=reg)
    def area(w, h):
        """Rectangle area."""
        return w * h

    w, h = sympy.Symbol("w", real=True), sympy.Symbol("h", real=True)
    assert area.symbolic.unwrap() == w * h
    parts = area.partials.unwrap()
    assert parts["w"] == h and parts["h"] == w
    tex = area.latex.unwrap()
    assert "partial" in tex and "aligned" in tex
    sens = area.sensitivities(_mk(reg, 2.0, 0.1), _mk(reg, 5.0, 0.1)).unwrap()
    assert sens == {"w": 5.0, "h": 2.0}
    assert area.__name__ == "area"


# frob:tests python/sadi/uncertainty/symbolic.py::trace
def test_untraceable_function_is_typed_error() -> None:
    """math.* on symbols cannot trace; result is Err with a fallback hint, not a raise."""
    reg = CovarianceRegistry()
    f = uncertain(lambda x: math.sin(x), registry=reg, method="analytic")
    r = f(_mk(reg, 1.0, 0.1))
    assert isinstance(r, Err) and r.danger_err is UncertainError.Untraceable
    assert "Monte Carlo" in r.danger_err.description
    assert isinstance(f.symbolic, Err)


# frob:tests python/sadi/uncertainty/symbolic.py::trace
def test_not_differentiable_and_signature_errors() -> None:
    """Varargs functions and non-differentiable ones give typed errors."""
    reg = CovarianceRegistry()
    assert (
        uncertain(lambda *a: a[0], registry=reg).symbolic.unwrap_err()
        is UncertainError.BadSignature
    )
    g = uncertain(lambda x: sympy.floor(x) * x, registry=reg)
    assert g.symbolic.unwrap_err() is UncertainError.NotDifferentiable


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__call__
def test_argument_errors_and_units() -> None:
    """Non-Measured, wrong arity, mixed dimensions, domain errors and explicit units."""
    reg = CovarianceRegistry()
    f = uncertain(lambda x, y: x + y, registry=reg)
    m = _mk(reg, 1.0, 0.1)
    assert f(m, 2.0).unwrap_err() is UncertainError.NotMeasured  # ty: ignore[invalid-argument-type]
    assert f(m).unwrap_err() is UncertainError.Arity
    assert f(m, _mk(reg, 1.0, 0.1, "s")).unwrap_err() is UncertainError.MixedDimensions
    inv = uncertain(lambda x: 1 / x, registry=reg)
    assert inv(_mk(reg, 0.0, 0.1)).unwrap_err() is UncertainError.NonFiniteResult
    s = uncertain(lambda x: sympy.sin(x), registry=reg)
    assert s(m).unwrap_err() is UncertainError.UnitNotInferred
    assert (
        uncertain(unit="bogus!", registry=reg)(lambda x: x)(m).unwrap_err()
        is UncertainError.UnitNotInferred
    )
    ok = uncertain(lambda x: sympy.sin(x), unit="dimensionless", registry=reg)(m)
    assert math.isclose(ok.unwrap().std_unc, math.cos(1.0) * 0.1)
    dimless = uncertain(lambda x: sympy.sin(x), registry=reg)(_mk(reg, 1.0, 0.1, "dimensionless"))
    assert dimless.is_ok


# frob:tests python/sadi/uncertainty/cache.py::KeyedCache.clear
# frob:tests python/sadi/uncertainty/cache.py::KeyedCache
# frob:tests python/sadi/uncertainty/symbolic.py::output_unit
# frob:tests python/sadi/uncertainty/symbolic.py::latex_derivation
# frob:tests python/sadi/uncertainty/symbolic.py::evaluate
# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__init__
# frob:tests python/sadi/uncertainty/uncertain.py::uncertain
# frob:tests python/sadi/uncertainty/uncertain.py::uncertain[dup2]
# frob:tests python/sadi/uncertainty/uncertain.py::uncertain[dup3]
# frob:tests python/sadi/uncertainty/cache.py::KeyedCache.__len__
# frob:tests python/sadi/uncertainty/cache.py::KeyedCache.__init__
def test_cache_reuses_compiled_expression() -> None:
    """Second call hits the trace and unit caches; errors are not cached."""
    TRACE_CACHE.clear()
    UNIT_CACHE.clear()
    reg = CovarianceRegistry()
    f = uncertain(lambda x: x**2, registry=reg)
    f(_mk(reg, 2.0, 0.1)).unwrap()
    f(_mk(reg, 3.0, 0.1)).unwrap()
    assert len(TRACE_CACHE) == 1 and TRACE_CACHE.hits >= 1
    assert UNIT_CACHE.hits == 1 and len(UNIT_CACHE) == 1
    f(_mk(reg, 3.0, 0.1, "s")).unwrap()
    assert len(UNIT_CACHE) == 2
    c: KeyedCache[int, int, str] = KeyedCache("t")
    assert c.get_or_compute(1, lambda: typani.Err("e")).is_err
    assert len(c) == 0


# frob:tests python/sadi/uncertainty/errors.py::hint
def test_hint_direct() -> None:
    """hint() returns the description for an UncertaintyError member."""
    assert hint(UncertaintyError.ZeroValue) == UncertaintyError.ZeroValue.description


def test_name_hygiene() -> None:
    """`uncertain` coexists with typani; no public sadi.uncertainty name equals a typani export."""
    from typani import propagate  # noqa: F401

    assert callable(unc.uncertain)
    assert not (set(unc.__all__) & set(dir(typani)))


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__call__
@settings(max_examples=60, deadline=None)
@given(POS, UNC, POS, UNC)
def test_hypothesis_product_closed_form(xv: float, xu: float, yv: float, yu: float) -> None:
    """x*y matches the closed-form independent RSS."""
    reg = CovarianceRegistry()
    f = uncertain(lambda a, b: a * b, registry=reg)
    out = f(_mk(reg, xv, xu), _mk(reg, yv, yu)).unwrap()
    assert math.isclose(out.std_unc, math.hypot(yv * xu, xv * yu), rel_tol=1e-9, abs_tol=1e-12)
