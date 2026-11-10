"""Tests for the gauge-height planner (docs/design/planner-gui.md)."""

# creates:python/tests/design/test_height_plan.py
# frob:ticket 01M7305JYQ6AZA2Z92Y5QQ54BF

from __future__ import annotations

import math

import pytest
from typani import Err, Ok

from sadi.design.cli import format_height_plan, main
from sadi.design.gui import plan_from_form
from sadi.design.height_plan import HeightPlanError, parse_heights, plan_heights

INV = "0.001:1e-5,0.002:1e-5,0.002:2e-5,0.003:1e-5,0.004:1e-5"


# frob:tests python/sadi/design/height_plan.py::parse_heights
def test_parse_heights_distinct_ids_and_errors() -> None:
    """Duplicates stay distinct ids; bad text is a clear error."""
    hs = parse_heights("0.1:0.001,0.1:0.002,0.2").unwrap()
    assert [h.height_id for h in hs] == ["h1", "h2", "h3"]
    assert hs[2].u_height_m == 1e-4  # blank u falls back to the 0.1 mm default
    assert isinstance(parse_heights("a:b"), Err)
    assert isinstance(parse_heights("0.1:-1"), Err)


# frob:tests python/sadi/design/height_plan.py::plan_heights
def test_plan_orders_heights_with_propagated_uncertainty() -> None:
    """Chosen heights each carry u and the final slope se matches the weighted-LS formula."""
    plan = plan_heights(parse_heights(INV).unwrap(), nominal_slope_v_per_m=-100.0).unwrap()
    assert [s.order for s in plan.steps] == list(range(1, len(plan.steps) + 1))
    assert all(s.u_height_m > 0 for s in plan.steps)
    chosen = list(plan.steps)
    w = [1.0 / (100.0 * s.u_height_m) ** 2 for s in chosen]
    xb = sum(wi * s.height_m for wi, s in zip(w, chosen, strict=True)) / sum(w)
    sxx = sum(wi * (s.height_m - xb) ** 2 for wi, s in zip(w, chosen, strict=True))
    assert plan.se_slope_v_per_m == pytest.approx(math.sqrt(1.0 / sxx))
    assert plan.se_offset_v is not None and plan.se_offset_v > 0
    # more points never loosen the slope
    ses = [s.se_slope_v_per_m for s in plan.steps if s.se_slope_v_per_m is not None]
    assert ses == sorted(ses, reverse=True)


# frob:tests python/sadi/design/height_plan.py::plan_heights
def test_duplicates_distinct_and_too_few_errors() -> None:
    """Under 2 distinct usable heights is an error; saturating heights are dropped."""
    same = parse_heights("0.001,0.001,0.001").unwrap()
    res = plan_heights(same, nominal_slope_v_per_m=-100.0)
    assert res == Err(HeightPlanError.TooFew)
    sat = parse_heights("0.001,0.002,1.0").unwrap()
    plan = plan_heights(sat, nominal_slope_v_per_m=-100.0, saturation_v=1.0).unwrap()
    assert plan.dropped_saturation == 4 and plan.n_usable == 3  # stacks with the 1.0 m height saturate
    assert plan_heights(sat, nominal_slope_v_per_m=0.0) == Err(HeightPlanError.ZeroSlope)
    three = parse_heights("0.001,0.002,0.003").unwrap()
    assert isinstance(plan_heights(three, nominal_slope_v_per_m=float("nan")), Err)
    many = parse_heights(",".join(str(0.001 * (i + 1)) for i in range(13))).unwrap()
    assert plan_heights(many, nominal_slope_v_per_m=-100.0) == Err(HeightPlanError.TooMany)


# frob:tests python/sadi/design/cli.py::main
def test_cli_heights(capsys) -> None:
    """--heights prints the height table; too few heights exits 1."""
    assert main(["--heights", INV, "--cal-slope", "-100"]) == 0
    out = capsys.readouterr().out
    assert "slope se=" in out and "h1" in out
    assert main(["--heights", INV]) == 0  # slope is optional
    assert main(["--heights", "0.001,0.001", "--cal-slope", "-100"]) == 1
    assert "at least 2 distinct" in capsys.readouterr().out
    plan = plan_heights(parse_heights(INV).unwrap(), nominal_slope_v_per_m=-100.0)
    assert isinstance(plan, Ok) and "pred_V" in format_height_plan(plan.value)


# frob:tests python/sadi/design/gui.py::plan_from_form
def test_gui_heights() -> None:
    """The form with a heights table returns height steps with se; errors are reported."""
    rep = plan_from_form({"heights": INV, "cal_slope": "-100"})
    assert rep["ok"] and rep["height_steps"] and rep["se_slope_v_per_m"] > 0
    assert plan_from_form({"heights": INV})["ok"]  # slope is optional
    assert not plan_from_form({"heights": "0.1,0.1", "cal_slope": "-100"})["ok"]


# frob:tests python/sadi/design/height_plan.py::plan_heights
def test_plan_without_slope_ranks_by_spread() -> None:
    plan = plan_heights(parse_heights("0.001,0.002,0.004,0.006").unwrap()).unwrap()
    assert not plan.slope_known and plan.rel_se_slope is not None and plan.se_slope_v_per_m is None
    assert plan.dropped_saturation == 0


# frob:tests python/sadi/design/height_plan.py::parse_heights
def test_parse_heights_blank_uncertainty_uses_default() -> None:
    hs = parse_heights("0.1,0.2:0.003").unwrap()
    assert [h.u_height_m for h in hs] == [1e-4, 0.003]
