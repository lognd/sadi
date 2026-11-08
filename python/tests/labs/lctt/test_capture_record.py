"""Capture yields LoadInputs with averaged volts that the driver records and replay reads."""

# frob:ticket 01M6WNEEBBBZVDZ6700RJDN26D
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from sadi.api.acquisition import AcquisitionDriver
from sadi.core.events import PointWindow
from sadi.core.pipeline import AcquisitionPipeline, PipelineConfig
from sadi.core.point_inputs import LoadInputs, parse_inputs
from sadi.labs.lctt.capture import CaptureConfig, CaptureController, CaptureMode
from sadi.labs.lctt.live import LoadPoint
from sadi.labs.lctt.settle import SettleConfig
from sadi.labs.lctt.settle_stream import StreamConfig
from sadi.server.curve_source import _event
from sadi.store.events import recover_state
from sadi.store.session import SessionMeta, create_session
from sadi.store.writer_thread import WriterHandle

SC = SettleConfig(window_s=10.0, threshold=1e-3, min_dwell_s=20.0)


class _NoSource:
    def next_block(self, timeout: float | None = 0.0) -> object:
        raise AssertionError("not streaming")


def _driver(sdir: Path) -> tuple[AcquisitionDriver, WriterHandle]:
    wal = WriterHandle.open(sdir / "wal", uuid.uuid4(), 1).danger_ok
    settle = SettleConfig(window_s=0.05, threshold=1.0, min_dwell_s=0.05, min_points=5)
    cfg = PipelineConfig(stream=StreamConfig(settle=settle), sample_rate_hz=1000.0, packet_len=8)
    return AcquisitionDriver(_NoSource(), AcquisitionPipeline(wal, cfg)), wal  # type: ignore[arg-type]


def _capture(mass: float, volts: float):
    ctl = CaptureController.create(
        StreamConfig(settle=SC),
        CaptureConfig(phase="load", mode=CaptureMode.AUTO, max_wait_s=500.0),
        lambda a, b: PointWindow(first_raw_seq=int(a), last_raw_seq=int(b) + 1),
        lambda: 0.0,
    ).danger_ok
    assert ctl.start_point(0.0, mass, 1e-4).is_ok
    times = [float(i) for i in range(60)]
    step = ctl.push(times, [volts + (1e-3 if i % 2 else -1e-3) for i in range(60)])
    cap = step.danger_ok.captured
    assert cap is not None
    return cap


# frob:tests python/sadi/labs/lctt/capture.py::CaptureController.start_point
# frob:tests python/sadi/labs/lctt/capture.py::CaptureController._window_volts
# frob:tests python/sadi/labs/lctt/capture.py::CaptureController._capture
def test_captured_inputs_average_window_volts() -> None:
    cap = _capture(2.0, 0.5)
    assert isinstance(cap.inputs, LoadInputs)
    assert cap.inputs.volts == pytest.approx(0.5, abs=1e-3)
    assert cap.inputs.mass_kg == 2.0 and cap.inputs.u_mass_kg == 1e-4
    assert 0.0 < cap.inputs.u_volts < 1e-3
    assert cap.point.inputs == cap.inputs.model_dump(exclude={"phase"})


# frob:tests python/sadi/labs/lctt/capture.py::Captured
def test_capture_run_replays_through_wal_and_curve_source(tmp_path: Path) -> None:
    sdir = create_session(tmp_path, SessionMeta(slug="cap")).danger_ok.path
    drv, wal = _driver(sdir)
    caps = [_capture(m, 0.1 * m) for m in (1.0, 2.0, 3.0)]
    for cap in caps:
        assert drv.record_point(cap.inputs, cap.point.window).is_ok
    assert wal.close().is_ok
    pts = recover_state(sdir).danger_ok.view().points
    assert len(pts) == 3
    for cp, cap in zip(pts, caps, strict=True):
        assert parse_inputs(cp.point.phase, cp.inputs).danger_ok == cap.inputs
        ev = _event(cp)
        assert isinstance(ev, LoadPoint)
        assert ev.volts == cap.inputs.volts and ev.mass_kg == cap.inputs.mass_kg
