"""Round trip: driver records phase-mapped POINTs, recover_state, then POST the fit."""

# frob:ticket 01M6WN40B3NY98XEFCEHNRCGB7
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from typani import Result

from sadi.api.acquisition import AcquisitionDriver
from sadi.core.events import PointWindow
from sadi.core.pipeline import AcquisitionPipeline, PipelineConfig
from sadi.core.point_inputs import (
    CalibrationInputs,
    LoadInputs,
    PointInputs,
    SpecimenInputs,
    TareInputs,
    parse_inputs,
)
from sadi.labs.lctt.settle import SettleConfig
from sadi.labs.lctt.settle_stream import StreamConfig
from sadi.server.app import AppSettings, create_app
from sadi.server.curve_source import make_curve_source
from sadi.store.events import recover_state
from sadi.store.session import SessionMeta, create_session
from sadi.store.writer_thread import WriterHandle

K = 1.0e-3
WINDOW = PointWindow(first_raw_seq=1, last_raw_seq=1)


class _NoSource:
    def next_block(self, timeout: float | None = 0.0) -> Result[Any, Any]:
        raise AssertionError("not streaming")

    def stop_streaming(self) -> Result[list[Any], Any]:
        raise AssertionError("not streaming")


def _driver(sdir: Path) -> tuple[AcquisitionDriver, WriterHandle]:
    wal = WriterHandle.open(sdir / "wal", uuid.uuid4(), 1).danger_ok
    settle = SettleConfig(window_s=0.05, threshold=1.0, min_dwell_s=0.05, min_points=5)
    cfg = PipelineConfig(stream=StreamConfig(settle=settle), sample_rate_hz=1000.0, packet_len=8)
    return AcquisitionDriver(_NoSource(), AcquisitionPipeline(wal, cfg)), wal


def _inputs() -> list[PointInputs]:
    out: list[PointInputs] = [
        CalibrationInputs(volts=float(v), height=0.08 + K * v) for v in range(5)
    ]
    out.append(TareInputs(mean=0.0, sd=0.001, n=100))
    out.append(SpecimenInputs(diameter=0.005, u_diameter=1e-6, hanger_kg=0.1))
    out += [
        LoadInputs(volts=0.01 * (i + 1) + (1e-4 if i % 2 else 0), mass_kg=float(i + 1))
        for i in range(8)
    ]
    return out


def test_record_recover_fit_round_trip(tmp_path: Path) -> None:
    """Points written by the driver replay in order and feed a successful fit."""
    # frob:tests python/sadi/api/acquisition.py::AcquisitionDriver.record_point
    # frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.record_point
    # frob:tests python/sadi/core/point_inputs.py::build_point
    # frob:tests python/sadi/core/point_inputs.py::parse_inputs
    sdir = create_session(tmp_path, SessionMeta(slug="rt")).danger_ok.path
    drv, wal = _driver(sdir)
    for inp in _inputs():
        assert drv.record_point(inp, WINDOW).is_ok
    assert wal.close().is_ok
    state = recover_state(sdir).danger_ok.view()
    assert [p.point.phase for p in state.points[:7]] == ["calibration"] * 5 + ["tare", "specimen"]
    assert all(p.point.phase == "load" for p in state.points[7:])
    for cp, inp in zip(state.points, _inputs(), strict=True):
        assert parse_inputs(cp.point.phase, cp.inputs).danger_ok == inp
    # The fit route requires an open session (NoOpenSession -> 409); report the one recorded above
    # as open so the guard itself stays untouched.  # frob:ticket 01M727MN00JSPCXQEE716A2XW6
    source = make_curve_source(lambda: sdir)
    c = TestClient(
        create_app(AppSettings(data_root=tmp_path, require_root_lock=False, curve_source=source))
    )
    res = c.post("/api/stress-strain/fit", json={"first": 1, "last": 6})
    assert res.status_code == 200, res.text
    assert res.json()["modulusMpa"] > 0


def test_parse_rejects_missing_keys() -> None:
    """A point missing a required key is an Err naming it, not a crash."""
    # frob:tests python/sadi/core/point_inputs.py::parse_inputs
    assert parse_inputs("calibration", {"volts": 1.0}).is_err
    assert parse_inputs("tare", {"mean": 1.0}).is_err
    assert parse_inputs("specimen", {}).is_err
    assert parse_inputs("load", {"volts": 1.0}).is_err
