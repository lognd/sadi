"""Tests for sadi.core.inventory."""

# frob:ticket 01M6W7R26WGJ0TZ4GS8N0YH4FG

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st
from typani import Err, Ok

from sadi.core.errors import ComputeCode, InputCode
from sadi.core.inventory import (
    GroupWeighed,
    Inventory,
    MassSource,
    WeightSet,
    parse_event,
)


def _inv(*events: WeightSet | GroupWeighed) -> Inventory:
    """Fold events into an inventory, failing the test on any Err."""
    inv = Inventory()
    for e in events:
        r = inv.record(e)
        assert isinstance(r, Ok), r
        inv = r.danger_ok
    return inv


def _w(n: int, mass: float = 1.0, u: float = 0.01, h: float = 0.02, uh: float = 0.001) -> WeightSet:
    return WeightSet(number=n, mass=mass, u_mass=u, height=h, u_height=uh)


# frob:tests python/sadi/core/inventory.py::Inventory.record
def test_entry_edit_keeps_history() -> None:
    inv = _inv(_w(1, 1.0), _w(2, 2.0), _w(1, 1.1))
    assert inv.weights()[1].mass == 1.1
    assert [e.mass for e in inv.history(1)] == [1.0, 1.1]
    assert len(inv.events) == 3


# frob:tests python/sadi/core/inventory.py::parse_event
def test_event_json_round_trip_and_bad() -> None:
    e = _w(3, 0.5)
    r = parse_event(e.model_dump_json())
    assert isinstance(r, Ok) and r.danger_ok == e
    g = GroupWeighed(name="a", numbers=(1, 2), mass=3.0, u_mass=0.01)
    assert parse_event(g.model_dump_json()).danger_ok == g
    bad = parse_event('{"type": "weight_set", "number": 0}')
    assert isinstance(bad, Err) and bad.danger_err.code is InputCode.OUT_OF_RANGE


# frob:tests python/sadi/core/inventory.py::Inventory.record
def test_record_rejects_bad_groups() -> None:
    inv = _inv(_w(1))
    unknown = inv.record(GroupWeighed(name="g", numbers=(1, 9), mass=1.0, u_mass=0.1))
    assert isinstance(unknown, Err) and unknown.danger_err.code is InputCode.UNKNOWN_ID
    dup = inv.record(GroupWeighed(name="g", numbers=(1, 1), mass=1.0, u_mass=0.1))
    assert isinstance(dup, Err) and dup.danger_err.code is InputCode.DUPLICATE


# frob:tests python/sadi/core/inventory.py::Inventory.combo
def test_combo_individual_only_rss() -> None:
    inv = _inv(_w(1, 1.0, 0.03, 0.02, 0.004), _w(2, 2.0, 0.04, 0.03, 0.003))
    c = inv.combo([1, 2]).unwrap()
    assert c.mass.value == pytest.approx(3.0)
    assert c.mass.standard_uncertainty == pytest.approx(0.05)
    assert c.height.value == pytest.approx(0.05)
    assert c.height.standard_uncertainty == pytest.approx(0.005)
    assert c.mass.unit == "kg" and c.height.unit == "m"
    assert c.source is MassSource.INDIVIDUAL


# frob:tests python/sadi/core/inventory.py::Inventory.combo
def test_combo_errors() -> None:
    inv = _inv(_w(1))
    assert inv.combo([]).danger_err.code is InputCode.MISSING
    assert inv.combo([1, 1]).danger_err.code is InputCode.DUPLICATE
    assert inv.combo([5]).danger_err.code is InputCode.UNKNOWN_ID


# frob:tests python/sadi/core/inventory.py::Inventory.combo
def test_group_beats_individual_when_more_precise() -> None:
    """Q7: precise group reading and noisy individuals -> reconciled estimate wins."""
    inv = _inv(
        _w(1, 1.0, 0.1),
        _w(2, 2.0, 0.1),
        GroupWeighed(name="pair", numbers=(1, 2), mass=3.02, u_mass=0.001),
    )
    c = inv.combo([1, 2]).unwrap()
    ind = next(x for x in c.choices if x.source is MassSource.INDIVIDUAL)
    grp = next(x for x in c.choices if x.source is MassSource.GROUP)
    assert ind.u_mass == pytest.approx(math.hypot(0.1, 0.1))
    assert grp.u_mass == 0.001
    assert c.mass.standard_uncertainty <= grp.u_mass
    assert c.mass.value == pytest.approx(3.02, abs=1e-3)
    assert c.source is MassSource.COMBINED


# frob:tests python/sadi/core/inventory.py::Inventory.combo
def test_individual_beats_group_when_more_precise() -> None:
    """Q7: precise individuals and a noisy group reading -> individual estimate kept."""
    inv = _inv(
        _w(1, 1.0, 0.001),
        _w(2, 2.0, 0.001),
        GroupWeighed(name="pair", numbers=(1, 2), mass=3.0, u_mass=0.5),
    )
    c = inv.combo([1, 2]).unwrap()
    assert c.mass.value == pytest.approx(3.0, abs=1e-5)
    assert c.mass.standard_uncertainty <= math.hypot(0.001, 0.001) * (1 + 1e-9)


# frob:tests python/sadi/core/inventory.py::Inventory.combo
def test_correlated_group_terms_subset() -> None:
    """A subset of a group has correlated posterior masses; variance must include cov."""
    inv = _inv(
        _w(1, 1.0, 0.1),
        _w(2, 1.0, 0.1),
        GroupWeighed(name="pair", numbers=(1, 2), mass=2.0, u_mass=0.05),
    )
    rec = inv.reconcile().unwrap()
    assert rec.covariance[0][1] < 0.0  # constraint anti-correlates the members
    c1 = inv.combo([1]).unwrap()
    c12 = inv.combo([1, 2]).unwrap()
    naive = math.hypot(c1.choices[-1].u_mass, inv.combo([2]).unwrap().choices[-1].u_mass)
    assert c12.choices[-1].u_mass < naive
    assert c12.choices[-1].u_mass == pytest.approx(
        math.sqrt(sum(sum(row) for row in rec.covariance))
    )


# frob:tests python/sadi/core/inventory.py::Inventory.reconcile
def test_inconsistent_group_warns() -> None:
    inv = _inv(
        _w(1, 1.0, 0.01),
        _w(2, 2.0, 0.01),
        GroupWeighed(name="bad", numbers=(1, 2), mass=3.5, u_mass=0.01),
    )
    rec = inv.reconcile().unwrap()
    assert len(rec.warnings) == 1 and rec.warnings[0].group == "bad"
    assert abs(rec.warnings[0].z) > 2
    assert inv.combo([1]).unwrap().warnings
    ok = _inv(_w(1), GroupWeighed(name="g", numbers=(1,), mass=1.0, u_mass=0.01))
    assert ok.reconcile().unwrap().warnings == ()


# frob:tests python/sadi/core/inventory.py::Inventory.reconcile
def test_exact_redundant_group_is_degenerate() -> None:
    inv = _inv(_w(1, 1.0, 0.0), GroupWeighed(name="g", numbers=(1,), mass=1.0, u_mass=0.0))
    r = inv.reconcile()
    assert isinstance(r, Err) and r.danger_err.code is ComputeCode.DEGENERATE


# frob:tests python/sadi/core/inventory.py::Inventory.to_weight_inventory
def test_to_weight_inventory() -> None:
    inv = _inv(_w(1, 1.0), _w(2, 2.0))
    wi = inv.to_weight_inventory().unwrap()
    assert [w.id for w in wi.weights] == ["1", "2"]
    assert wi.get("2").unwrap().mass == 2.0


# frob:tests python/sadi/core/inventory.py::Inventory.combo
@given(
    masses=st.lists(st.floats(0.1, 10.0), min_size=2, max_size=5),
    u=st.floats(0.001, 0.2),
    ug=st.floats(0.001, 0.2),
    offset=st.floats(-0.1, 0.1),
)
def test_posterior_never_worse_than_either_estimate(
    masses: list[float], u: float, ug: float, offset: float
) -> None:
    ws = [_w(i + 1, m, u) for i, m in enumerate(masses)]
    nums = tuple(range(1, len(masses) + 1))
    g = GroupWeighed(name="all", numbers=nums, mass=sum(masses) + offset, u_mass=ug)
    inv = _inv(*ws, g)
    c = inv.combo(list(nums)).unwrap()
    ind_u = u * math.sqrt(len(masses))
    assert c.mass.standard_uncertainty <= min(ind_u, ug) * (1 + 1e-6)
    lo, hi = sorted((sum(masses), g.mass))
    assert lo - 1e-9 <= c.mass.value <= hi + 1e-9 or c.source is MassSource.INDIVIDUAL
