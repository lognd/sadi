"""Tests for the streaming settle layer on simulator-style synthetic LVDT scenarios."""

# frob:ticket 01M6W8Z1JAJTQR9KHPMH1A73VD

from __future__ import annotations

import math
import random
from collections.abc import Callable

import pytest
from pydantic import ValidationError
from typani import Err, Ok

from sadi.labs.lctt.settle import SettleConfig, SettleError
from sadi.labs.lctt.settle_stream import (
    PointRecord,
    SettleMode,
    SettleState,
    StreamConfig,
    StreamError,
    StreamingSettleDetector,
    StreamStatus,
)

SC = SettleConfig(window_s=10.0, threshold=1e-3, min_dwell_s=20.0)
CFG = StreamConfig(settle=SC)
Signal = Callable[[float], float]


def _clean(t: float) -> float:
    return 1.0 - math.exp(-t / 15.0)


def _noisy(seed: int) -> Signal:
    rng = random.Random(seed)
    return lambda t: 0.5 + rng.gauss(0, 0.5)


def _creeping(t: float) -> float:
    return 0.5 * math.log1p(t / 5.0)  # slope 0.1/(5+t): above 1e-3 for 300 s


def _drifting(t: float) -> float:
    return 0.01 * t


def _stream(
    det: StreamingSettleDetector, sig: Signal, n: int, block: int = 7, t0: float = 0.0
) -> list[StreamStatus]:
    """Feed n 1 Hz samples in blocks, returning each block's status."""
    out: list[StreamStatus] = []
    for s in range(0, n, block):
        ts = [t0 + i for i in range(s, min(n, s + block))]
        r = det.push(ts, [sig(a - t0) for a in ts])
        assert isinstance(r, Ok)
        out.append(r.danger_ok)
    return out


def _detector(cfg: StreamConfig = CFG) -> StreamingSettleDetector:
    det = StreamingSettleDetector(cfg)
    assert isinstance(det.mark_load_change(0.0), Ok)
    return det


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector
# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.raw
# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.close_point
def test_clean_settles_within_dwell() -> None:
    det = _detector()
    states = _stream(det, _clean, 200)
    assert states[0].state is SettleState.LOADING
    assert SettleState.CREEPING in [s.state for s in states]
    last = states[-1]
    assert last.state is SettleState.SETTLED
    assert last.time_since_load is not None and last.time_since_load < 100.0
    assert last.drift_rate is not None and abs(last.drift_rate.value) <= SC.threshold
    rec = det.close_point()
    assert isinstance(rec, Ok)
    r = rec.danger_ok
    assert r.settled and not r.forced_early
    assert r.window_end is not None and r.window_start is not None
    assert r.window_end - r.window_start <= SC.window_s
    assert r.time_since_load == last.time_since_load


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector
@pytest.mark.parametrize("sig", [_noisy(1), _noisy(2), _creeping, _drifting])
def test_no_false_settle(sig: Signal) -> None:
    det = _detector()
    states = _stream(det, sig, 300)
    assert all(s.state is not SettleState.SETTLED for s in states)
    assert states[-1].state is SettleState.CREEPING
    rec = det.close_point().danger_ok
    assert not rec.settled and not rec.forced_early


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector
def test_drifting_reports_drift_rate() -> None:
    det = _detector()
    last = _stream(det, _drifting, 100)[-1]
    assert last.drift_rate is not None
    assert last.drift_rate.value == pytest.approx(0.01)
    assert last.time_since_load == pytest.approx(99.0)


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector
def test_block_size_independent() -> None:
    a, b = _detector(), _detector()
    sa = _stream(a, _clean, 200, block=1)[-1]
    sb = _stream(b, _clean, 200, block=50)[-1]
    assert sa.state is sb.state is SettleState.SETTLED
    assert sa.time_since_load == sb.time_since_load


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.mark_load_change
def test_load_change_resets_and_records_raw() -> None:
    det = _detector()
    _stream(det, _clean, 150)
    assert det.status.state is SettleState.SETTLED
    # Second load step at t=150: signal moves again, state returns to loading.
    assert isinstance(det.mark_load_change(150.0), Ok)
    assert det.status.state is SettleState.LOADING
    ts = [150.0 + i for i in range(3)]
    r = det.push(ts, [_clean(0.0)] * 3)
    assert isinstance(r, Ok) and r.danger_ok.state is SettleState.LOADING
    assert r.danger_ok.point_index == 1
    assert len(det.records) == 1 and det.records[0].settled
    raw_t, raw_y = det.raw
    assert len(raw_t) == len(raw_y) == 153  # raw recorded in every state


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.mark_load_change
def test_marker_closes_unsettled_point_and_samples_before_marker_are_raw_only() -> None:
    det = StreamingSettleDetector(CFG)
    assert isinstance(det.push([0.0, 1.0], [0.0, 0.0]), Ok)
    assert det.status.state is SettleState.LOADING and det.status.point_index is None
    assert isinstance(det.mark_load_change(1.5), Ok)
    assert isinstance(det.push([2.0, 3.0], [0.0, 0.0]), Ok)
    assert isinstance(det.mark_load_change(5.0), Ok)
    rec = det.records[0]
    assert not rec.settled and not rec.forced_early and rec.n_samples == 2
    assert det.raw[0] == (0.0, 1.0, 2.0, 3.0)


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.force_early
def test_force_early_flags_point() -> None:
    det = _detector()
    _stream(det, _creeping, 60)
    rec = det.force_early()
    assert isinstance(rec, Ok)
    r: PointRecord = rec.danger_ok
    assert r.forced_early and not r.settled
    assert r.drift_rate is not None and r.time_since_load == pytest.approx(59.0)
    assert det.status.point_index == 1  # the next point opens automatically


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.force_early
def test_force_after_settle_is_not_forced_early() -> None:
    det = _detector()
    _stream(det, _clean, 200)
    r = det.force_early().danger_ok
    assert r.settled and not r.forced_early


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamConfig
def test_fixed_dwell_mode_ignores_drift() -> None:
    cfg = StreamConfig(settle=SC, mode=SettleMode.FIXED_DWELL, fixed_dwell_s=40.0)
    det = _detector(cfg)
    states = _stream(det, _drifting, 100)  # drifting would never pass the drift criterion
    assert states[2].state is not SettleState.SETTLED  # t=20
    assert states[-1].state is SettleState.SETTLED
    assert states[-1].time_since_load == pytest.approx(40.0)
    r = det.close_point().danger_ok
    assert r.settled and not r.forced_early and r.mode is SettleMode.FIXED_DWELL
    assert r.drift_rate is not None


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamConfig
def test_config_validation_and_frozen() -> None:
    with pytest.raises(ValidationError):
        StreamConfig(settle=SC, mode=SettleMode.FIXED_DWELL)
    with pytest.raises(ValidationError):
        StreamConfig(settle=SC, fixed_dwell_s=0.0)
    with pytest.raises(ValidationError):
        CFG.mode = SettleMode.FIXED_DWELL  # ty: ignore[invalid-assignment]


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.push
def test_push_rejects_bad_blocks_without_recording() -> None:
    det = _detector()
    assert det.push([0.0, 1.0], [0.0]) == Err(SettleError.LengthMismatch)
    assert det.push([0.0, math.nan], [0.0, 0.0]) == Err(SettleError.NonFinite)
    assert det.push([1.0, 1.0], [0.0, 0.0]) == Err(SettleError.NonMonotonicTime)
    assert isinstance(det.push([5.0], [0.0]), Ok)
    assert det.push([5.0], [0.0]) == Err(SettleError.NonMonotonicTime)
    assert det.raw == ((5.0,), (0.0,))


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.mark_load_change
def test_bad_markers_and_no_open_point() -> None:
    det = StreamingSettleDetector(CFG)
    assert det.close_point() == Err(StreamError.NoOpenPoint)
    assert det.mark_load_change(math.nan) == Err(StreamError.BadMarker)
    assert isinstance(det.mark_load_change(10.0), Ok)
    assert det.mark_load_change(5.0) == Err(StreamError.BadMarker)


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.__init__
# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.records
# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.status
def test_fresh_detector_status_and_records() -> None:
    det = StreamingSettleDetector(CFG)
    assert det.records == ()
    assert det.status == StreamStatus(state=SettleState.LOADING)
    assert det.raw == ((), ())
    assert isinstance(det.mark_load_change(0.0), Ok)
    assert det.status.point_index == 0
    _stream(det, _clean, 200)
    rec = det.close_point().danger_ok
    assert det.records == (rec,)
    assert det.status.point_index == 1


def _step_then_ramp(t: float) -> float:
    return 0.0 if t < 100 else 0.01 * (t - 100)


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.push
def test_settle_verdict_does_not_latch() -> None:
    det = _detector()
    st = _stream(det, _step_then_ramp, 220)
    assert any(x.state is SettleState.SETTLED for x in st)
    assert st[-1].state is not SettleState.SETTLED
    rec = det.close_point().danger_ok
    assert not rec.settled


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.close_point
def test_point_opens_automatically_after_capture_and_resettles() -> None:
    det = _detector()
    _stream(det, _clean, 200)
    assert det.close_point().danger_ok.settled
    assert det.status.point_index == 1
    assert det.status.state is not SettleState.SETTLED
    r = det.push([200.0 + i for i in range(1, 200)], [0.0] * 199)
    assert r.danger_ok.state is SettleState.SETTLED
    assert det.close_point().danger_ok.point_index == 1
