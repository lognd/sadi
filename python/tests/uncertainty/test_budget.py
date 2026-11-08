"""Tests for the uncertainty budget: per-input rows, ranking, exact sum with correlation."""

# frob:ticket 01M6W7R2BS0R89GW39HM0XPX0J

from __future__ import annotations

import json
import math

from hypothesis import given, settings
from hypothesis import strategies as st
from typani import Err

from sadi.uncertainty import CovarianceRegistry, Measured, UncertainError, uncertain

POS = st.floats(min_value=0.5, max_value=50.0, allow_nan=False, allow_infinity=False)
UNC = st.floats(min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False)
RHO = st.floats(min_value=-0.95, max_value=0.95, allow_nan=False)


def _mk(reg: CovarianceRegistry, v: float, u: float) -> Measured:
    """Create a Measured in registry `reg`."""
    return Measured.create(v, u, "m", registry=reg).unwrap()


# frob:tests python/sadi/uncertainty/budget.py::build_budget
def test_rows_independent_ranked() -> None:
    """Independent inputs: contribution = (c u)^2, ranked, percents sum to 100."""
    reg = CovarianceRegistry()
    f = uncertain(lambda x, y: x * y, unit="m**2", registry=reg)
    x, y = _mk(reg, 3.0, 0.1), _mk(reg, 4.0, 0.5)
    b = f.budget(x, y).unwrap()
    assert [r.name for r in b.rows] == ["y", "x"]
    assert [r.rank for r in b.rows] == [1, 2]
    top = b.rows[0]
    assert math.isclose(top.sensitivity, 3.0)
    assert math.isclose(top.contribution, (3.0 * 0.5) ** 2)
    assert top.cross == 0.0
    assert math.isclose(sum(r.percent for r in b.rows), 100.0)
    assert b.dominant == top


# frob:tests python/sadi/uncertainty/budget.py::Budget.payload
# frob:tests python/sadi/uncertainty/budget.py::Budget.dominant
def test_payload_json_serialisable() -> None:
    """The UI payload round-trips through json."""
    reg = CovarianceRegistry()
    f = uncertain(lambda x, y: x + y, registry=reg)
    p = f.budget(_mk(reg, 1.0, 0.1), _mk(reg, 2.0, 0.2)).unwrap().payload()
    back = json.loads(json.dumps(p))
    assert back["dominant"] == "y"
    assert len(back["rows"]) == 2
    assert {"name", "value", "std_unc", "sensitivity", "contribution", "percent"} <= set(
        back["rows"][0]
    )


# frob:tests python/sadi/uncertainty/budget.py::build_budget
def test_cross_terms_attributed() -> None:
    """Correlated a+b: cross terms are shown and contributions still sum to u^2."""
    reg = CovarianceRegistry()
    f = uncertain(lambda a, b: a + b, registry=reg)
    a, b = _mk(reg, 2.0, 0.3), _mk(reg, 1.0, 0.4)
    a.correlate(b, -0.8, reg).unwrap()
    bud = f.budget(a, b).unwrap()
    assert all(r.cross != 0.0 for r in bud.rows)
    assert math.isclose(sum(r.contribution for r in bud.rows), f(a, b).unwrap().std_unc ** 2)


# frob:tests python/sadi/uncertainty/budget.py::build_budget
def test_zero_total_variance() -> None:
    """All-zero uncertainty yields zero percents, not a division error."""
    reg = CovarianceRegistry()
    f = uncertain(lambda a, b: a * b, unit="m**2", registry=reg)
    bud = f.budget(_mk_zero(reg), _mk_zero(reg)).unwrap()
    assert bud.total_variance == 0.0
    assert all(r.percent == 0.0 for r in bud.rows)


def _mk_zero(reg: CovarianceRegistry) -> Measured:
    """Create an exact (u = 0) Measured."""
    return Measured.create(2.0, 0.0, "m", registry=reg).unwrap()


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.budget
def test_errors_propagate() -> None:
    """Bad arguments surface as typed errors, not exceptions."""
    f = uncertain(lambda a, b: a + b)
    assert isinstance(f.budget(1.0, 2.0), Err)  # ty: ignore[invalid-argument-type]  # deliberately bad arguments
    reg = CovarianceRegistry()
    assert f.budget(_mk(reg, 1.0, 0.1)).err is UncertainError.Arity


# frob:tests python/sadi/uncertainty/budget.py::build_budget
@settings(max_examples=100, deadline=None)
@given(
    vals=st.tuples(POS, POS, POS),
    uncs=st.tuples(UNC, UNC, UNC),
    rhos=st.tuples(RHO, RHO, RHO),
)
def test_budget_sums_to_total_variance(
    vals: tuple[float, ...], uncs: tuple[float, ...], rhos: tuple[float, ...]
) -> None:
    """Property: rows sum to u^2 of the result and to total_variance, with correlation."""
    reg = CovarianceRegistry()
    f = uncertain(lambda x, y, z: x * y / z + x, unit="m", registry=reg)
    ms = [_mk(reg, v, u) for v, u in zip(vals, uncs, strict=True)]
    # Only apply a correlation set that keeps C positive semi-definite.
    for (i, j), r in zip([(0, 1), (0, 2), (1, 2)], rhos, strict=True):
        ms[i].correlate(ms[j], r * 0.4, reg).unwrap()
    bud = f.budget(*ms).unwrap()
    total = f(*ms).unwrap().std_unc ** 2
    s = math.fsum(r.contribution for r in bud.rows)
    assert math.isclose(s, bud.total_variance, rel_tol=1e-12, abs_tol=1e-300)
    assert math.isclose(s, total, rel_tol=1e-9, abs_tol=1e-12)
    assert math.isclose(math.fsum(r.direct + r.cross for r in bud.rows), s, rel_tol=1e-12)
    mags = [abs(r.contribution) for r in bud.rows]
    assert mags == sorted(mags, reverse=True)
