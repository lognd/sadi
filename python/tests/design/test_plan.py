"""Tests for the weight-subset planner (docs/design/weight-plan.md)."""

# frob:ticket 01M72X7S8DA8X3Q95HRYNKT2ED

from __future__ import annotations

import math

from typani import Err

from sadi.design.models import CapturedPoint, DesignPhase, PlanRequest, Weight
from sadi.design.plan import MAX_WEIGHTS, PlanError, plan
from sadi.labs.lctt.loading import STANDARD_G
from sadi.labs.lctt.saturation import DEFAULT_SATURATION_V

MASSES = (0.02, 0.05, 0.05, 0.1, 0.1, 0.2, 0.01, 0.03)
AREA = math.pi * 2.019e-4**2 / 4.0


def _weights(masses=MASSES, u=1e-4):
    return tuple(Weight(weight_id=f"w{i}", mass_kg=m, u_mass_kg=u) for i, m in enumerate(masses))


def _req(masses=MASSES, **kw) -> PlanRequest:
    base = dict(
        weights=_weights(masses),
        diameter_m=2.019e-4,
        u_diameter_m=2e-6,
        length_m=0.083,
        u_length_m=1e-3,
        cal_slope_v_per_m=-2000.0,
    )
    base.update(kw)
    return PlanRequest(**base)


# frob:tests python/sadi/design/plan.py::plan
def test_plan_orders_hangs_and_reports_uncertainty() -> None:
    """Hangs ascend, carry quadrature mass uncertainty and a reason, and E gets a half-width."""
    p = plan(_req()).unwrap()
    masses = [h.total_mass_kg for h in p.hangs]
    assert masses == sorted(masses) and len(masses) >= 3
    for h in p.hangs:
        assert (
            h.u_mass_kg == math.sqrt(len(h.weight_ids)) * 1e-4
            or abs(h.u_mass_kg - math.sqrt(len(h.weight_ids)) * 1e-4) < 1e-12
        )
        assert h.reason.startswith(f"Hang #{h.order}")
    assert p.hangs[-1].e_half_width_pa is not None and p.hangs[-1].e_half_width_pa > 0
    assert p.phase is DesignPhase.ELASTIC


# frob:tests python/sadi/design/plan.py::plan
def test_duplicates_are_distinct_ids_and_deduped_to_lowest() -> None:
    """Equal-mass multisets collapse to one load that uses the lowest ids."""
    p = plan(_req((0.1, 0.1, 0.1))).unwrap()
    assert p.n_achievable == 3  # 0.1, 0.2, 0.3
    used = [h.weight_ids for h in p.hangs]
    assert ("w0",) in used or p.hangs[0].weight_ids == ("w0",)
    for h in p.hangs:
        assert len(set(h.weight_ids)) == len(h.weight_ids)
        assert h.weight_ids == tuple(f"w{i}" for i in range(len(h.weight_ids)))


# frob:tests python/sadi/design/plan.py::plan
def test_saturation_clipping() -> None:
    """A huge calibration slope saturates heavy hangs; none exceeds the threshold."""
    req = _req(cal_slope_v_per_m=-2.0e5)
    p = plan(req).unwrap()
    assert p.dropped_saturation > 0
    assert all(abs(h.predicted_volts) <= DEFAULT_SATURATION_V for h in p.hangs)


# frob:tests python/sadi/design/plan.py::plan
def test_capacity_clipping() -> None:
    """Tension stays under the capacity fraction of the ultimate load."""
    p = plan(_req((0.1, 0.2, 0.5, 1.0))).unwrap()
    assert p.dropped_capacity > 0
    assert all(h.tension_n <= 0.95 * 132e6 * AREA for h in p.hangs)
    assert all(h.tension_n == h.total_mass_kg * STANDARD_G for h in p.hangs)


# frob:tests python/sadi/design/plan.py::plan
def test_fewer_usable_weights_than_eight() -> None:
    """With a few small weights the planner still returns a (shorter) plan."""
    p = plan(_req((0.05, 0.1))).unwrap()
    assert 1 <= len(p.hangs) <= 3 and p.n_inventory == 2
    assert plan(_req((0.5,))).unwrap_err() is PlanError.NoUsableHang


# frob:tests python/sadi/design/plan.py::plan
def test_no_usable_hang_is_an_error() -> None:
    """Everything saturating gives a typed error, not an empty plan."""
    r = plan(_req(cal_slope_v_per_m=-1e9))
    assert isinstance(r, Err) and r.unwrap_err() is PlanError.NoUsableHang


# frob:tests python/sadi/design/plan.py::plan
def test_input_errors() -> None:
    """Empty, oversized, duplicate-id and non-finite inputs are Result errors."""
    assert plan(_req(())).unwrap_err() is PlanError.NoWeights
    assert plan(_req((0.01,) * (MAX_WEIGHTS + 1))).unwrap_err() is PlanError.TooManyWeights
    dup = _req(weights=(Weight(weight_id="a", mass_kg=0.1), Weight(weight_id="a", mass_kg=0.1)))
    assert plan(dup).unwrap_err() is PlanError.DuplicateIds
    assert plan(_req(cal_slope_v_per_m=float("nan"))).unwrap_err() is PlanError.NonFinite


# frob:tests python/sadi/design/plan.py::plan
def test_deterministic() -> None:
    """Identical requests give identical plans."""
    assert plan(_req()).unwrap() == plan(_req()).unwrap()


# frob:tests python/sadi/design/plan.py::plan
def test_replan_from_captured_points() -> None:
    """Captured points set the floor: later hangs are heavier than anything captured."""
    first = plan(_req()).unwrap()
    k = _req().config.selector.n_min_linear
    cap = tuple(
        CapturedPoint(mass_kg=h.total_mass_kg, volts=h.predicted_volts, u_volts=h.u_predicted_volts)
        for h in first.hangs[:k]
    )
    again = plan(_req(captured=cap)).unwrap()
    floor = max(c.mass_kg for c in cap)
    assert again.hangs and all(h.total_mass_kg > floor for h in again.hangs)
    assert again.hangs[0].slope_half_width_v_per_kg is not None
