"""Tests for the LCTT guided run engine (synthetic simulator-driven three-phase run)."""

# frob:ticket 01M6W7R3W8RJPVS0VVDG2YNMJB

from __future__ import annotations

from typing import TypeVar

import pytest
from typani import Err, Ok, Result

from sadi.core.results import ResultSet
from sadi.labs.lctt.guidance import (
    MAX_RUN_POINTS,
    GuidanceConfig,
    GuidanceError,
    GuidanceInput,
    GuidedRun,
    HoldState,
    LoadRange,
    LoadSuggestion,
    Phase,
    guide,
    make_range,
)
from sadi.labs.lctt.live import (
    CalPoint,
    LiveEngine,
    LiveEvent,
    LoadPoint,
    SpecimenSetup,
    TareBlock,
)

_T = TypeVar("_T")
_E = TypeVar("_E")
SLOPE = 0.01
L0 = 0.08313
RANGE = LoadRange(min_kg=0.5, max_kg=4.0)


def _setup(n_cal: int) -> list[LiveEvent]:
    ev: list[LiveEvent] = [
        CalPoint(volts=float(i), height=0.05 + SLOPE * i + (1e-6 if i % 2 else -1e-6))
        for i in range(n_cal)
    ]
    ev.append(TareBlock(mean=0.1, sd=0.001, n=50))
    ev.append(SpecimenSetup(diameter=0.01, u_diameter=1e-5, hanger_kg=0.5, u_hanger_kg=1e-3))
    return ev


def _point(i: int, mass: float) -> LoadPoint:
    eps = 4e-4 * mass + (1e-6 if i % 3 else 0.0)
    return LoadPoint(
        point_id=f"p{i}", volts=0.1 + eps * L0 / SLOPE, u_volts=1e-4, mass_kg=mass, u_mass_kg=1e-4
    )


def _ok(r: Result[_T, _E]) -> _T:
    assert isinstance(r, Ok), r
    return r.danger_ok


def _inp(rs: ResultSet, n_cal: int = 0, hold: HoldState = HoldState.READY) -> GuidanceInput:
    return GuidanceInput(results=rs, n_cal_points=n_cal, hold=hold)


# frob:tests python/sadi/labs/lctt/guidance.py::guide
# frob:tests python/sadi/labs/lctt/guidance.py::EvenScheduleSuggester.suggest
def test_next_action_text_per_hold_state() -> None:
    empty = ResultSet()
    cfg = GuidanceConfig(load_range=RANGE)
    assert _ok(guide(Phase.ELASTIC, _inp(empty, hold=HoldState.CREEPING), cfg)).next_action == (
        "Wait: creeping"
    )
    assert (
        _ok(guide(Phase.PLASTIC, _inp(empty, hold=HoldState.AWAITING_ACCEPT), cfg)).next_action
        == "Press Space to accept"
    )
    cal = _ok(guide(Phase.CALIBRATE, _inp(empty, n_cal=1), cfg))
    assert "calibration point 2" in cal.next_action
    el = _ok(guide(Phase.ELASTIC, _inp(empty), cfg))
    assert el.suggested_load_kg is not None and RANGE.contains(el.suggested_load_kg)
    assert "kg" in el.next_action


class _WeightsSuggester:
    """Plugin-style suggester producing combination text."""

    def suggest(
        self, phase: Phase, results: ResultSet, load_range: LoadRange
    ) -> Result[LoadSuggestion, GuidanceError]:
        return Ok(LoadSuggestion(load_kg=2.0, text="Use weights 3, 5, 6"))


# frob:tests python/sadi/labs/lctt/guidance.py::LoadSuggester
# frob:tests python/sadi/labs/lctt/guidance.py::LoadSuggester.suggest
def test_custom_suggester_text_is_used() -> None:
    cfg = GuidanceConfig(load_range=RANGE)
    st = _ok(guide(Phase.ELASTIC, _inp(ResultSet()), cfg, _WeightsSuggester()))
    assert st.next_action == "Use weights 3, 5, 6"
    assert st.suggested_load_kg == 2.0


class _BadSuggester:
    def __init__(self, kg: float) -> None:
        self.kg = kg

    def suggest(
        self, phase: Phase, results: ResultSet, load_range: LoadRange
    ) -> Result[LoadSuggestion, GuidanceError]:
        return Ok(LoadSuggestion(load_kg=self.kg, text="x"))


# frob:tests python/sadi/labs/lctt/guidance.py::guide
@pytest.mark.parametrize("kg", [100.0, -1.0, float("nan"), float("inf")])
def test_unsafe_suggestion_is_refused(kg: float) -> None:
    cfg = GuidanceConfig(load_range=RANGE)
    out = guide(Phase.ELASTIC, _inp(ResultSet()), cfg, _BadSuggester(kg))
    assert isinstance(out, Err)
    assert out.danger_err is GuidanceError.UnsafeLoad


# frob:tests python/sadi/labs/lctt/guidance.py::make_range
# frob:tests python/sadi/labs/lctt/guidance.py::check_target
def test_bad_range_and_target() -> None:
    assert isinstance(make_range(3.0, 1.0), Err)
    assert isinstance(make_range(float("nan"), 1.0), Err)
    assert isinstance(make_range(0.0, 1.0), Ok)
    out = guide(Phase.ELASTIC, _inp(ResultSet()), GuidanceConfig(target=0.0))
    assert isinstance(out, Err)
    assert out.danger_err is GuidanceError.BadTarget


def _elastic_results(n: int) -> ResultSet:
    eng = LiveEngine()
    last = ResultSet()
    for ev in [*_setup(5), *[_point(i, 0.5 + 0.3 * i) for i in range(n)]]:
        last = _ok(eng.add(ev))
    return last


# frob:tests python/sadi/labs/lctt/guidance.py::GuidedRun.guide
# frob:tests python/sadi/labs/lctt/guidance.py::guide
def test_confidence_and_stop_early_proposed_not_forced() -> None:
    rs = _elastic_results(8)
    loose = GuidanceConfig(target=10.0, load_range=RANGE)
    st = _ok(guide(Phase.ELASTIC, _inp(rs), loose))
    assert st.confidence.met and st.confidence.fraction == 1.0
    assert st.stop_early and st.proposed_next_phase is Phase.PLASTIC
    assert st.expected_value is not None and st.unit == "Pa"
    # the user ignores it: guidance still offers a next load and the phase is unchanged
    assert st.suggested_load_kg is not None
    run = GuidedRun(loose)
    run.guide(_inp(rs))
    assert run.phase is Phase.CALIBRATE

    tight = GuidanceConfig(target=1e-9, load_range=RANGE)
    st2 = _ok(guide(Phase.ELASTIC, _inp(rs), tight))
    assert not st2.confidence.met and 0.0 <= st2.confidence.fraction < 1.0
    assert not st2.stop_early and st2.proposed_next_phase is None
    assert st2.confidence.half_width is not None


# frob:tests python/sadi/labs/lctt/guidance.py::GuidedRun
# frob:tests python/sadi/labs/lctt/guidance.py::GuidedRun.phase
# frob:tests python/sadi/labs/lctt/guidance.py::GuidedRun.__init__
def test_accept_transition_walks_phases_then_errs() -> None:
    run = GuidedRun()
    assert _ok(run.accept_transition()) is Phase.ELASTIC
    assert _ok(run.accept_transition()) is Phase.PLASTIC
    out = run.accept_transition()
    assert isinstance(out, Err) and out.danger_err is GuidanceError.NoNextPhase


def _cal(i: int) -> CalPoint:
    return CalPoint(volts=float(i), height=0.05 + SLOPE * i + (1e-6 if i % 2 else -1e-6))


def _drive_phase(run: GuidedRun, cfg: GuidanceConfig) -> int:
    """Follow the guide in the run's current phase until it proposes moving on or the cap."""
    eng = LiveEngine()
    rs = ResultSet()
    n_cal = 0
    taken = 0
    if run.phase is not Phase.CALIBRATE:
        for ev in [*(_cal(i) for i in range(5)), *_setup(0)]:
            eng.add(ev)
    for _ in range(MAX_RUN_POINTS):
        st = _ok(run.guide(_inp(rs, n_cal)))
        if st.suggested_load_kg is not None:
            assert cfg.load_range.contains(st.suggested_load_kg)
        if st.proposed_next_phase is not None or st.points_taken >= st.max_points:
            return taken
        taken += 1
        if run.phase is Phase.CALIBRATE:
            rs = _ok(eng.add(_cal(n_cal)))
            n_cal += 1
        else:
            assert st.suggested_load_kg is not None
            rs = _ok(eng.add(_point(taken, st.suggested_load_kg)))
    raise AssertionError("phase did not finish within the documented bound")


# frob:tests python/sadi/labs/lctt/guidance.py::GuidedRun
@pytest.mark.parametrize("target", [0.5, 1e-9])
def test_full_three_phase_run_is_bounded_and_safe(target: float) -> None:
    cfg = GuidanceConfig(target=target, load_range=RANGE)
    run = GuidedRun(cfg)
    total = 0
    for _ in range(3):
        total += _drive_phase(run, cfg)
        if run.phase is not Phase.PLASTIC:
            _ok(run.accept_transition())
    assert total <= MAX_RUN_POINTS
    assert MAX_RUN_POINTS == 35
    if target < 1e-6:
        assert total == MAX_RUN_POINTS  # target never met: the cap is what ends the run
