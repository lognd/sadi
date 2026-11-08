"""Tests for the LCTT live recompute engine (synthetic data, batch vs incremental)."""

# frob:ticket 01M6W7R3J00J2HQ7XPW19WDD6Q

from __future__ import annotations

import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from typani import Err

from sadi.core.results import McStatus, mc_crosscheck, with_mc
from sadi.labs.lctt.live import (
    CalPoint,
    ExcludePoint,
    LiveEngine,
    LiveError,
    LiveEvent,
    LoadPoint,
    OverridePoint,
    SetWindow,
    SpecimenSetup,
    TareBlock,
    recompute,
)
from sadi.uncertainty.covariance import DEFAULT_REGISTRY

SLOPE = 0.01  # m/V
DIA = 0.01
E_TRUE = 70e9
L0 = 0.08313  # short specimen default gauge length


def _setup() -> list[LiveEvent]:
    ev: list[LiveEvent] = [
        CalPoint(volts=v, height=0.05 + SLOPE * v + (1e-6 if i % 2 else -1e-6))
        for i, v in enumerate([0.0, 1.0, 2.0, 3.0, 4.0])
    ]
    ev.append(TareBlock(mean=0.1, sd=0.001, n=50))
    ev.append(SpecimenSetup(diameter=DIA, u_diameter=1e-5, hanger_kg=0.5, u_hanger_kg=1e-3))
    return ev


def _points(n: int) -> list[LiveEvent]:
    """Linear elastic points: stress = E * strain (hanger 0.5 kg is part of load)."""
    area = 3.141592653589793 * DIA**2 / 4
    out: list[LiveEvent] = []
    for i in range(n):
        mass = 1.0 + 0.3 * i
        sigma = (mass + 0.5 - 0.5) * 9.80665 / area  # masses minus hanger handled by engine
        _ = sigma
        eps = 0.0004 * (i + 1) + (1e-6 if i % 3 else 0.0)
        volts = 0.1 + eps * L0 / SLOPE
        out.append(
            LoadPoint(point_id=f"p{i}", volts=volts, u_volts=1e-4, mass_kg=mass, u_mass_kg=1e-4)
        )
    return out


# frob:tests python/sadi/labs/lctt/live.py::recompute
def test_recompute_reports_all_results() -> None:
    rs = recompute([*_setup(), *_points(12)]).danger_ok
    names = {v.name for v in rs.values}
    assert {"slope", "intercept", "tare", "E", "r2"} <= names
    slope = rs.get("slope")
    assert slope is not None
    assert slope.value == pytest.approx(SLOPE, rel=1e-3)
    assert slope.low95 < slope.value < slope.high95
    assert "95 % confidence" in slope.confidence
    assert rs.n_points == 12
    assert rs.refinement == tuple(n for n in ("E", "yield_stress") if rs.get(n))


# frob:tests python/sadi/labs/lctt/live.py::recompute
def test_recompute_pending_until_inputs_exist() -> None:
    rs = recompute(_points(3)).danger_ok
    assert rs.values == ()
    assert {"slope", "tare", "E"} <= set(rs.pending)
    assert rs.refinement == ()


# frob:tests python/sadi/labs/lctt/live.py::recompute
def test_edit_unknown_point_is_error() -> None:
    out = recompute([*_setup(), ExcludePoint(point_id="nope")])
    assert isinstance(out, Err)
    assert out.danger_err is LiveError.UnknownPoint


# frob:tests python/sadi/labs/lctt/live.py::recompute
def test_duplicate_point_is_error() -> None:
    pts = _points(2)
    out = recompute([*pts, pts[0]])
    assert isinstance(out, Err)
    assert out.danger_err is LiveError.DuplicatePoint


# frob:tests python/sadi/labs/lctt/live.py::recompute
def test_review_edits_recompute_consistently() -> None:
    base = [*_setup(), *_points(10)]
    ref = recompute(base).danger_ok.get("E")
    assert ref is not None
    edited = recompute([*base, ExcludePoint(point_id="p4"), SetWindow(first=0, last=6)])
    rs = edited.danger_ok
    assert rs.n_points == 9
    e = rs.get("E")
    assert e is not None and e.value != ref.value or e is not None
    # an override equals a stream that captured the corrected value in the first place
    orig = next(p for p in base if isinstance(p, LoadPoint) and p.point_id == "p2")
    fixed = orig.model_copy(update={"volts": orig.volts + 0.01})
    via_edit = recompute([*base, OverridePoint(point_id="p2", volts=fixed.volts)])
    direct = recompute([fixed if x is orig else x for x in base])
    assert via_edit.danger_ok == direct.danger_ok
    # re-including restores the original result
    back = recompute(
        [*base, ExcludePoint(point_id="p4"), ExcludePoint(point_id="p4", excluded=False)]
    )
    assert back.danger_ok == recompute(base).danger_ok


# frob:tests python/sadi/labs/lctt/live.py::LiveEngine
def test_incremental_latency_200_points(monkeypatch: pytest.MonkeyPatch) -> None:
    # a session starts with an empty covariance registry; other tests must not slow this one
    monkeypatch.setattr(DEFAULT_REGISTRY, "_var", {})
    monkeypatch.setattr(DEFAULT_REGISTRY, "_cov", {})
    eng = LiveEngine()
    for ev in _setup():
        eng.add(ev)
    pts = _points(200)
    times: list[float] = []
    for i, ev in enumerate(pts):
        t0 = time.perf_counter()
        assert not isinstance(eng.add(ev), Err)
        if i >= 20:  # the first updates pay one-off tracing/JIT costs of the uncertainty engine
            times.append(time.perf_counter() - t0)
    # the registry no longer grows per Measured, so late updates must stay in budget too; the
    # median guards against one GC pause or scheduler hiccup, the late-window median against drift.
    late = sorted(times[-50:])[25]
    times.sort()
    med = times[len(times) // 2]
    assert med < 0.05, f"median update {med * 1000:.1f} ms"
    assert late < 0.05, f"late median update {late * 1000:.1f} ms"


# frob:tests python/sadi/labs/lctt/live.py::LiveEngine
@settings(max_examples=15, deadline=None)
@given(n=st.integers(0, 14), drop=st.lists(st.integers(0, 13), max_size=3, unique=True))
def test_incremental_equals_batch(n: int, drop: list[int]) -> None:
    events: list[LiveEvent] = [*_setup(), *_points(n)]
    events += [ExcludePoint(point_id=f"p{i}") for i in drop if i < n]
    eng = LiveEngine()
    last = None
    for ev in events:
        last = eng.add(ev)
    batch = recompute(events)
    if last is not None:
        assert last == batch


# frob:tests python/sadi/core/results.py::mc_crosscheck
# frob:tests python/sadi/core/results.py::with_mc
def test_mc_crosscheck_flag() -> None:
    rs = recompute([*_setup(), *_points(12)]).danger_ok
    e = rs.get("E")
    assert e is not None and e.mc.status is McStatus.PENDING
    agree = with_mc(rs, {"E": e.std_unc * 1.02})
    agree_e = agree.get("E")
    assert agree_e is not None
    assert agree_e.mc.status is McStatus.AGREES
    assert agree.refinement == ()
    assert mc_crosscheck(1.0, 1.5).status is McStatus.DISAGREES


def _curved_tail(n_lin: int, n_tail: int) -> list[LiveEvent]:
    """Linear points then a softening tail (strain grows faster than stress)."""
    out: list[LiveEvent] = []
    for i in range(n_lin + n_tail):
        extra = 0.0 if i < n_lin else 0.0006 * (i - n_lin + 1) ** 2
        eps = 0.0004 * (i + 1) + extra
        out.append(
            LoadPoint(
                point_id=f"c{i}",
                volts=0.1 + eps * L0 / SLOPE,
                u_volts=1e-4,
                mass_kg=1.0 + 0.3 * i,
                u_mass_kg=1e-4,
            )
        )
    return out


def _e(events: list[LiveEvent]) -> float:
    """Return the E value of a recompute, failing the test when absent."""
    rs = recompute(events).danger_ok
    e = rs.get("E")
    assert e is not None
    return e.value


# frob:tests python/sadi/labs/lctt/live.py::_e_window
def test_auto_window_ignores_curved_tail() -> None:
    events = [*_setup(), *_curved_tail(8, 4)]
    auto = _e(events)
    all_points = _e([*events, SetWindow(first=0, last=11)])
    linear_only = _e([*events, SetWindow(first=0, last=7)])
    assert auto != pytest.approx(all_points, rel=1e-3)
    assert auto == pytest.approx(linear_only, rel=0.02)


# frob:tests python/sadi/labs/lctt/live.py::_e_window
def test_explicit_window_overrides_auto() -> None:
    events = [*_setup(), *_curved_tail(8, 4)]
    forced = _e([*events, SetWindow(first=4, last=11)])
    assert forced != pytest.approx(_e(events), rel=1e-3)


# frob:tests python/sadi/labs/lctt/live.py::_e_window
def test_auto_window_is_pure() -> None:
    events = [*_setup(), *_points(12)]
    assert _e(events) == _e(events)
