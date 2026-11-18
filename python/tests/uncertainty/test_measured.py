"""Tests for sadi.uncertainty: Measured, units, covariance, coverage and name hygiene."""

from __future__ import annotations

import math

import typani
from hypothesis import given
from hypothesis import strategies as st
from typani import Err, Ok, Result

import sadi.uncertainty as unc
from sadi.uncertainty import (
    CovarianceRegistry,
    Measured,
    UncertaintyError,
    effective_dof,
    hint,
    interval95,
    relative_uncertainty,
    t95,
    units,
)

FLOATS = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
POS = st.floats(min_value=1e-3, max_value=1e6, allow_nan=False, allow_infinity=False)
UNC = st.floats(min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False)


def _mk(value: float, u: float, unit: str = "m", dof: float | None = None) -> Measured:
    """Create a Measured in a throwaway registry-free path, asserting success."""
    r = Measured.create(value, u, unit, dof=dof, registry=CovarianceRegistry())
    return r.unwrap()


def _ok(r: Result[Measured, UncertaintyError]) -> Measured:
    """Unwrap an Ok result in tests."""
    return r.unwrap()


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.create
def test_si_conversion() -> None:
    """Millimetres convert to metres, uncertainty included."""
    m = _mk(1500.0, 2.0, "mm")
    assert math.isclose(m.value, 1.5) and math.isclose(m.std_unc, 0.002)
    assert m.unit == "m"


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.create
def test_offset_unit_uncertainty_is_a_difference() -> None:
    """degC converts to kelvin for the value but not for the uncertainty."""
    m = _mk(20.0, 0.5, "degC")
    assert math.isclose(m.value, 293.15) and math.isclose(m.std_unc, 0.5)


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.create
def test_bad_inputs_return_errors() -> None:
    """Unknown units and invalid numbers are Err values, not exceptions."""
    assert Measured.create(1.0, 0.1, "furlongs/fortnightx").err is UncertaintyError.UnknownUnit
    assert Measured.create(math.nan, 0.1).err is UncertaintyError.InvalidValue
    assert Measured.create(1.0, -1.0).err is UncertaintyError.InvalidUncertainty
    assert Measured.create(1.0, 1.0, dof=0).err is UncertaintyError.InvalidDof
    assert hint(UncertaintyError.DimensionMismatch)


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.add
def test_dimension_mismatch_is_err() -> None:
    """Adding metres to seconds returns DimensionMismatch without raising."""
    r = _mk(1.0, 0.1, "m") + _mk(1.0, 0.1, "s")
    assert isinstance(r, Err) and r.danger_err is UncertaintyError.DimensionMismatch


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.mul
def test_product_units_and_uncertainty() -> None:
    """Force = mass * acceleration carries kg*m/s^2 and relative RSS."""
    m, a = _mk(2.0, 0.02, "kg"), _mk(9.0, 0.09, "m/s**2")
    f = _ok(m * a)
    assert math.isclose(f.value, 18.0)
    assert math.isclose(f.std_unc, 18.0 * math.hypot(0.01, 0.01), rel_tol=1e-9)
    assert units_equal(f.unit, "N")


def units_equal(a: str, b: str) -> bool:
    """Return True if two unit strings are the same dimension and scale."""
    from sadi.uncertainty import units

    pa, pb = units.parse_unit(a).unwrap(), units.parse_unit(b).unwrap()
    return bool(pa.dimensionality == pb.dimensionality)


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/covariance.py::first_order_variance
def test_self_subtraction_is_exactly_zero() -> None:
    """x - x has zero variance because both operands share an id."""
    x = Measured.create(5.0, 1.0, "m").unwrap()
    d = _ok(x - x)
    assert d.value == 0.0 and d.std_unc == 0.0


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/covariance.py::CovarianceRegistry.register_derived
def test_derived_keeps_correlation_with_sources() -> None:
    """(x + y) - y has the uncertainty of x, via cov(x + y, y)."""
    x = Measured.create(5.0, 1.0, "m").unwrap()
    y = Measured.create(3.0, 2.0, "m").unwrap()
    s = _ok(x + y)
    back = _ok(s - y)
    assert math.isclose(back.value, 5.0) and math.isclose(back.std_unc, 1.0)


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.correlate
def test_declared_correlation_changes_sum() -> None:
    """rho=1 adds uncertainties linearly, rho=-1 cancels equal ones."""
    x = Measured.create(1.0, 1.0, "m").unwrap()
    y = Measured.create(1.0, 1.0, "m").unwrap()
    assert x.correlate(y, 1.0).is_ok
    assert math.isclose(_ok(x + y).std_unc, 2.0)
    assert x.correlate(y, -1.0).is_ok
    assert math.isclose(_ok(x + y).std_unc, 0.0, abs_tol=1e-12)
    assert x.correlate(y, 1.5).err is UncertaintyError.InvalidCorrelation


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.div
def test_division_by_zero_and_bad_power_are_errs() -> None:
    """Division by zero and sqrt of a negative return DomainError."""
    x = _mk(1.0, 0.1, "m")
    assert (x / 0.0).err is UncertaintyError.DomainError
    assert _mk(-4.0, 0.1).power(0.5).err is UncertaintyError.DomainError
    assert x.power(math.inf).err is UncertaintyError.InvalidExponent


# frob:tests python/sadi/uncertainty/measured.py::Measured.from_json
# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.to_json
def test_json_round_trip_and_bad_json() -> None:
    """to_json/from_json preserve every field; garbage gives BadJson."""
    m = Measured.create(2.5, 0.1, "kg", dof=7.0).unwrap()
    back = Measured.from_json(m.to_json()).unwrap()
    assert back == m
    assert Measured.from_json("{nope").err is UncertaintyError.BadJson
    assert Measured.from_json('{"value": 1, "std_unc": -1}').err is UncertaintyError.BadJson


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/coverage.py::t95
def test_t95_known_values() -> None:
    """t95 matches tables and tends to 1.96."""
    assert math.isclose(t95(10).unwrap(), 2.2281388, rel_tol=1e-6)
    assert math.isclose(t95(None).unwrap(), 1.959964, rel_tol=1e-6)
    assert t95(0).err is UncertaintyError.InvalidDof


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/coverage.py::effective_dof
def test_welch_satterthwaite_example() -> None:
    """Two equal contributions with dof 4 and 6 combine per the W-S formula."""
    r = effective_dof([(1.0, 4.0), (1.0, 6.0)]).unwrap()
    assert math.isclose(r, 4.0 / (1 / 4 + 1 / 6))
    assert effective_dof([(1.0, None)]).unwrap() == math.inf
    assert effective_dof([]).err is UncertaintyError.NoContributions


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/coverage.py::relative_uncertainty
def test_relative_uncertainty_zero_value() -> None:
    """Relative uncertainty of zero is ZeroValue; otherwise |u/x|."""
    assert relative_uncertainty(0.0, 1.0).err is UncertaintyError.ZeroValue
    assert relative_uncertainty(-4.0, 1.0).unwrap() == 0.25


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/coverage.py::interval95
@given(v=FLOATS, u=UNC, dof=st.one_of(st.none(), st.floats(min_value=1, max_value=1e4)))
def test_interval_is_symmetric_and_widens_with_small_dof(
    v: float, u: float, dof: float | None
) -> None:
    """The 95% interval is centred on the value and at least 1.96 u wide per side."""
    lo, hi = interval95(v, u, dof).unwrap()
    assert math.isclose((lo + hi) / 2, v, rel_tol=1e-9, abs_tol=1e-6)
    assert (hi - lo) / 2 >= 1.959 * u - 1e-9


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.add
@given(a=FLOATS, ua=UNC, b=FLOATS, ub=UNC)
def test_add_rss_property(a: float, ua: float, b: float, ub: float) -> None:
    """Independent sum has value a+b and uncertainty hypot(ua, ub)."""
    s = _ok(_mk(a, ua) + _mk(b, ub))
    assert math.isclose(s.value, a + b, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(s.std_unc, math.hypot(ua, ub), rel_tol=1e-9, abs_tol=1e-9)


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.mul
@given(a=POS, ua=UNC, b=POS, ub=UNC)
def test_mul_div_relative_property(a: float, ua: float, b: float, ub: float) -> None:
    """Relative uncertainty of a*b and a/b is hypot(ua/a, ub/b)."""
    x, y = _mk(a, ua), _mk(b, ub)
    expected = math.hypot(ua / a, ub / b)
    for r, v in ((x * y, a * b), (x / y, a / b)):
        m = _ok(r)
        assert math.isclose(m.value, v, rel_tol=1e-9)
        assert math.isclose(m.std_unc / abs(v), expected, rel_tol=1e-6, abs_tol=1e-9)


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/measured.py::Measured.to_json
@given(v=FLOATS, u=UNC, dof=st.one_of(st.none(), st.floats(min_value=0.5, max_value=1e4)))
def test_json_round_trip_property(v: float, u: float, dof: float | None) -> None:
    """Any valid Measured survives JSON round trip unchanged."""
    m = _mk(v, u, "m", dof)
    assert Measured.from_json(m.to_json()).unwrap() == m


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/covariance.py::CovarianceRegistry.set_correlation
@given(rho=st.floats(min_value=-1, max_value=1), ua=POS, ub=POS)
def test_correlation_round_trip_property(rho: float, ua: float, ub: float) -> None:
    """set_correlation then correlation returns rho; covariance is symmetric."""
    reg = CovarianceRegistry()
    reg.register("a", ua**2)
    reg.register("b", ub**2)
    assert reg.set_correlation("a", "b", rho).is_ok
    assert math.isclose(reg.correlation("a", "b"), rho, abs_tol=1e-9)
    assert reg.covariance("a", "b") == reg.covariance("b", "a")


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/covariance.py::CovarianceRegistry.__init__
# frob:tests python/sadi/uncertainty/covariance.py::CovarianceRegistry.ids
# frob:tests python/sadi/uncertainty/measured.py::Measured.covariance_with
# frob:tests python/sadi/uncertainty/measured.py::Measured.relative_uncertainty
# frob:tests python/sadi/uncertainty/measured.py::Measured.interval95
# frob:tests python/sadi/uncertainty/measured.py::Measured.sub
# frob:tests python/sadi/uncertainty/measured.py::Measured.neg
# frob:tests python/sadi/uncertainty/measured.py::Measured.__add__
# frob:tests python/sadi/uncertainty/measured.py::Measured.__radd__
# frob:tests python/sadi/uncertainty/measured.py::Measured.__sub__
# frob:tests python/sadi/uncertainty/measured.py::Measured.__rsub__
# frob:tests python/sadi/uncertainty/measured.py::Measured.__mul__
# frob:tests python/sadi/uncertainty/measured.py::Measured.__rmul__
# frob:tests python/sadi/uncertainty/measured.py::Measured.__truediv__
# frob:tests python/sadi/uncertainty/measured.py::Measured.__rtruediv__
# frob:tests python/sadi/uncertainty/measured.py::Measured.__pow__
# frob:tests python/sadi/uncertainty/measured.py::Measured.__neg__
# frob:tests python/sadi/uncertainty/units.py::same_dimension
# frob:tests python/sadi/uncertainty/units.py::combine_units
# frob:tests python/sadi/uncertainty/units.py::power_unit
# frob:tests python/sadi/uncertainty/units.py::to_si
# frob:tests python/sadi/uncertainty/units.py::parse_unit
def test_operators_and_accessors() -> None:
    """Operator forms, reflected scalars, accessors and unit dimension checks agree."""
    reg = CovarianceRegistry()
    x = Measured.create(4.0, 0.4, "m", dof=5.0, registry=reg).unwrap()
    y = Measured.create(2.0, 0.2, "m", registry=reg).unwrap()
    assert math.isclose(_ok(x + y).value, 6.0) and math.isclose(_ok(x - y).value, 2.0)
    assert (10.0 + x).err is UncertaintyError.DimensionMismatch
    assert math.isclose(_ok(10.0 * x).value, 40.0) and math.isclose(_ok(x * 2).value, 8.0)
    assert math.isclose(_ok(x / y).value, 2.0) and math.isclose(_ok(x**2).value, 16.0)
    assert math.isclose(_ok(8.0 / x).value, 2.0) and math.isclose(_ok(-x).value, -4.0)
    z = Measured.create(3.0, 0.1, registry=reg).unwrap()
    assert math.isclose(_ok(10.0 - z).value, 7.0)
    assert math.isclose(_ok(x.neg()).std_unc, 0.4) and math.isclose(_ok(x.sub(y)).value, 2.0)
    assert x.covariance_with(x, reg) == x.std_unc**2
    assert math.isclose(x.relative_uncertainty().unwrap(), 0.1)
    lo, hi = x.interval95().unwrap()
    assert lo < 4.0 < hi and (hi - lo) / 2 > 1.96 * 0.4
    assert set(reg.ids()) >= {x.id, y.id}
    assert units.same_dimension("m", "mm").unwrap() is True
    assert units.same_dimension("m", "s").unwrap() is False
    assert units.combine_units("m", "s", "/").is_ok
    assert units.power_unit("m", 2.0).is_ok and units.power_unit("zzz", 2.0).is_err
    assert units.to_si(1.0, 0.0, "zzz").is_err and units.parse_unit("").is_ok
    assert units.same_dimension("m", "zzz").err is UncertaintyError.UnknownUnit


# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:tests python/sadi/uncertainty/errors.py::UncertaintyError
def test_no_typani_name_reuse() -> None:
    """The public API shares no name with typani, and both import together unaliased."""
    assert not set(unc.__all__) & set(typani.__all__)
    for banned in ("propagate", "catching"):
        assert not hasattr(unc, banned)
    assert isinstance(Ok(1), Ok)
    from typani import propagate  # noqa: F401

    if hasattr(unc, "uncertain"):
        assert unc.uncertain is not typani.propagate


# frob:ticket 01M6XAY79MWPV07858YAKSBJQ6
# frob:tests python/sadi/uncertainty/covariance.py::CovarianceRegistry.known
def test_registry_known_tracks_register_and_forget() -> None:
    """known() is True exactly while a variance is registered for the id."""
    reg = CovarianceRegistry()
    assert not reg.known("a")
    reg.register("a", 0.25)
    assert reg.known("a") and not reg.known("b")
    reg.forget("a")
    assert not reg.known("a")


# frob:ticket 01M72YKF3EN8RJX7RCH78JDPQC
# frob:tests python/sadi/uncertainty/measured.py::Measured.from_readings
def test_from_readings_rss():
    """Mean, type-A standard error and instrument term combine in quadrature."""
    from sadi.uncertainty.measured import Measured

    m = Measured.from_readings([1.0, 2.0, 3.0], 0.5, "m").danger_ok
    assert m.value == 2.0
    assert abs(m.std_unc - (1 / 3 + 0.25) ** 0.5) < 1e-12
    assert m.dof == 2


def test_from_readings_single_and_empty():
    """One reading has only the instrument term; none is an error."""
    from sadi.uncertainty.measured import Measured

    one = Measured.from_readings([5.0], 0.2).danger_ok
    assert abs(one.std_unc - 0.2) < 1e-12 and one.dof is None
    assert Measured.from_readings([]).is_err
