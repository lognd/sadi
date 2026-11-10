"""Tests for capture modes with a deterministic injected clock and synthetic LVDT."""

# frob:ticket 01M6W7R06C7F7ZN0RC4CV3NWW5

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from typani import Err

from sadi.labs.lctt.capture import (
    CaptureConfig,
    CaptureController,
    CaptureError,
    CaptureMode,
    set_window_edit,
)
from sadi.labs.lctt.settle import SettleConfig
from sadi.labs.lctt.settle_stream import SettleMode, StreamConfig
from sadi.store.events import PointWindow

SC = SettleConfig(window_s=10.0, threshold=1e-3, min_dwell_s=20.0)
DRIFT = StreamConfig(settle=SC)
FIXED = StreamConfig(settle=SC, mode=SettleMode.FIXED_DWELL, fixed_dwell_s=15.0)


class FakeClock:
    """Manually advanced clock."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def resolver(a: float, b: float) -> PointWindow | None:
    """Map time to seq at 10 Hz."""
    return PointWindow(first_raw_seq=int(a * 10), last_raw_seq=int(b * 10))


def block(t0: float, t1: float, f=lambda t: 0.0) -> tuple[list[float], list[float]]:
    """1 Hz samples in [t0, t1)."""
    ts = [float(i) for i in range(int(t0), int(t1))]
    return ts, [f(t) for t in ts]


def make(stream=DRIFT, **kw) -> tuple[CaptureController, FakeClock]:
    clock = FakeClock()
    cfg = CaptureConfig(phase="elastic", **kw)
    res = CaptureController.create(stream, cfg, resolver, clock)
    assert not isinstance(res, Err)
    ctl = res.danger_ok
    assert not isinstance(ctl.start_point(0.0, 1.0), Err)
    return ctl, clock


def decay(t: float) -> float:
    return math.exp(-t / 5.0)


# frob:tests python/sadi/labs/lctt/capture.py::CaptureController.push
# frob:tests python/sadi/labs/lctt/capture.py::CaptureController.accept
def test_confirm_never_auto_and_settled_accept() -> None:
    ctl, _ = make(mode=CaptureMode.CONFIRM)
    step = ctl.push(*block(0, 60))
    assert not isinstance(step, Err)
    assert step.danger_ok.captured is None
    cap = ctl.accept()
    assert not isinstance(cap, Err)
    c = cap.danger_ok
    assert c.point.settled and not c.point.forced_early and c.warnings == ()
    assert c.point.window.last_raw_seq > c.point.window.first_raw_seq


def test_accept_before_settled_is_forced_early_with_warning() -> None:
    ctl, _ = make(mode=CaptureMode.CONFIRM)
    ctl.push(*block(0, 15, decay))
    cap = ctl.accept()
    assert not isinstance(cap, Err)
    assert cap.danger_ok.point.forced_early and not cap.danger_ok.point.settled
    assert cap.danger_ok.warnings


def test_accept_without_point() -> None:
    ctl, _ = make(mode=CaptureMode.CONFIRM)
    ctl.push(*block(0, 60))
    assert not isinstance(ctl.accept(), Err)
    assert ctl.accept() == Err(CaptureError.NoRawRange)  # auto-opened point has no samples yet


def test_auto_captures_on_settle() -> None:
    ctl, _ = make(mode=CaptureMode.AUTO, max_wait_s=500.0)
    step = ctl.push(*block(0, 60))
    assert not isinstance(step, Err)
    cap = step.danger_ok.captured
    assert cap is not None and cap.point.settled and not cap.point.forced_early


# frob:tests python/sadi/labs/lctt/capture.py::CaptureController.tick
def test_auto_forced_at_max_wait() -> None:
    ctl, clock = make(mode=CaptureMode.AUTO, max_wait_s=30.0)
    step = ctl.push(*block(0, 15, decay))
    assert not isinstance(step, Err) and step.danger_ok.captured is None
    clock.now += 29.0
    tick = ctl.tick()
    assert not isinstance(tick, Err) and tick.danger_ok.captured is None
    clock.now += 1.0
    tick = ctl.tick()
    assert not isinstance(tick, Err)
    cap = tick.danger_ok.captured
    assert cap is not None and cap.point.forced_early and cap.warnings


def test_tick_after_capture_is_noop() -> None:
    ctl, _ = make(mode=CaptureMode.AUTO, max_wait_s=500.0)
    ctl.push(*block(0, 60))
    tick = ctl.tick()
    assert not isinstance(tick, Err) and tick.danger_ok.captured is None


# frob:ticket 01M72B7QAB5FFFNXRHZ80T48X8
# frob:tests python/sadi/labs/lctt/capture.py::CaptureController.tick
def test_auto_tick_and_push_after_auto_capture_do_not_assert() -> None:
    ctl, clock = make(mode=CaptureMode.AUTO, max_wait_s=500.0)
    first = ctl.push(*block(0, 60))
    assert not isinstance(first, Err) and first.danger_ok.captured is not None
    for _ in range(2):
        tick = ctl.tick()
        assert not isinstance(tick, Err) and tick.danger_ok.captured is None
    clock.now += 1000.0
    nxt = ctl.push(*block(60, 62))
    assert not isinstance(nxt, Err)


def test_fixed_dwell_captures_after_dwell() -> None:
    ctl, _ = make(FIXED, mode=CaptureMode.FIXED_DWELL)
    early = ctl.push(*block(0, 12, decay))
    assert not isinstance(early, Err) and early.danger_ok.captured is None
    late = ctl.push(*block(12, 20, decay))
    assert not isinstance(late, Err)
    cap = late.danger_ok.captured
    assert cap is not None and cap.point.settled and not cap.point.forced_early


# frob:tests python/sadi/labs/lctt/capture.py::CaptureController.create
# frob:tests python/sadi/labs/lctt/capture.py::CaptureController.__init__
def test_mode_mismatch() -> None:
    cfg = CaptureConfig(phase="p", mode=CaptureMode.FIXED_DWELL)
    assert CaptureController.create(DRIFT, cfg, resolver, FakeClock()) == Err(
        CaptureError.ModeMismatch
    )
    cfg = CaptureConfig(phase="p", mode=CaptureMode.CONFIRM)
    assert isinstance(CaptureController.create(FIXED, cfg, resolver, FakeClock()), Err)


def test_auto_requires_max_wait() -> None:
    with pytest.raises(ValidationError):
        CaptureConfig(phase="p", mode=CaptureMode.AUTO)


def test_missing_raw_range() -> None:
    clock = FakeClock()
    cfg = CaptureConfig(phase="p")
    ctl = CaptureController.create(DRIFT, cfg, lambda a, b: None, clock).danger_ok
    ctl.start_point(0.0, 1.0)
    ctl.push(*block(0, 60))
    assert ctl.accept() == Err(CaptureError.NoRawRange)


def test_window_edit_roundtrip_through_replay_args() -> None:
    ctl, _ = make(mode=CaptureMode.CONFIRM)
    ctl.push(*block(0, 60))
    pt = ctl.accept().danger_ok.point
    edit = set_window_edit(pt.point_id, PointWindow(first_raw_seq=5, last_raw_seq=50))
    assert edit.op == "set_window" and edit.target == pt.point_id
    assert edit.args["first_raw_seq"] == 5 and edit.args["last_raw_seq"] == 50
    assert "v" not in edit.args


# frob:tests python/sadi/labs/lctt/capture.py::CaptureController.detector
def test_detector_exposes_raw_and_records() -> None:
    ctl, _ = make(mode=CaptureMode.CONFIRM)
    ctl.push(*block(0, 60))
    ctl.accept()
    assert len(ctl.detector.raw[0]) == 60
    assert len(ctl.detector.records) == 1


# frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
# frob:tests python/sadi/labs/lctt/capture.py::CaptureController.tick
def test_auto_does_not_recapture_same_load_until_start_point() -> None:
    ctl, clock = make(mode=CaptureMode.AUTO, max_wait_s=30.0)
    first = ctl.push(*block(0, 60))
    assert not isinstance(first, Err) and first.danger_ok.captured is not None
    clock.now += 1000.0
    for _ in range(3):
        tick = ctl.tick()
        assert not isinstance(tick, Err) and tick.danger_ok.captured is None
    again = ctl.push(*block(60, 200))
    assert not isinstance(again, Err) and again.danger_ok.captured is None
    # a new load change re-arms the controller
    assert not isinstance(ctl.start_point(200.0, 2.0), Err)
    ctl.push(*block(200, 206, decay))
    clock.now += 31.0
    tick = ctl.tick()
    assert not isinstance(tick, Err) and tick.danger_ok.captured is not None
