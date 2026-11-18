"""Capture input and window validation, and the calibrate / clamp-slip completion gates."""

# frob:ticket 01M71WYRA3SN64B56Z6G13SHSE

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sadi.core.point_inputs import CalibrationInputs, SpecimenInputs, check_ranges, check_window
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.lab import calibration_gate, clamp_gate
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.store.events import PointWindow

WINDOW = {"first_raw_seq": 0, "last_raw_seq": 0}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with the lctt lab and an open session."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).status_code == 201
        yield c


def _post(c: TestClient, phase: str, inputs: dict[str, Any], window: Any = WINDOW) -> Any:
    """POST one capture."""
    body = {"phase": phase, "inputs": inputs, "window": window}
    return c.post(
        "/api/session/points",
        content=json.dumps(body),  # allow_nan so NaN/Inf reach the server as Python emits them
        headers={"content-type": "application/json"},
    )


# frob:tests python/sadi/core/point_inputs.py::check_ranges
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 1e308])
def test_check_ranges_rejects_non_finite_and_huge(bad: float) -> None:
    """NaN, Inf and absurd magnitudes never pass the range check."""
    assert check_ranges(CalibrationInputs(volts=bad, height=0.01)).is_err
    assert check_ranges(CalibrationInputs(volts=0.1, height=bad)).is_err


# frob:tests python/sadi/core/point_inputs.py::check_ranges
def test_check_ranges_unit_hints_and_negative_height() -> None:
    """A diameter in mm gets a unit hint; negative or huge heights are refused."""
    bad = check_ranges(SpecimenInputs(diameter=0.2, length=0.1))
    assert bad.is_err
    assert "millimetres" in bad.danger_err
    assert check_ranges(SpecimenInputs(diameter=0.0002, length=0.1)).is_ok
    assert check_ranges(CalibrationInputs(volts=0.1, height=-0.01)).is_err
    assert check_ranges(CalibrationInputs(volts=0.1, height=50.0)).is_err
    assert check_ranges(CalibrationInputs(volts=0.1, height=0.01)).is_ok


# frob:tests python/sadi/core/point_inputs.py::check_window
def test_check_window() -> None:
    """Negative, reversed and (when bounded) beyond-durable windows are refused."""
    ok = PointWindow(first_raw_seq=1, last_raw_seq=5)
    assert check_window(ok).is_ok
    assert check_window(ok, 5).is_ok
    assert check_window(ok, 4).is_err
    assert check_window(PointWindow(first_raw_seq=-1, last_raw_seq=5)).is_err
    assert check_window(PointWindow(first_raw_seq=6, last_raw_seq=5)).is_err
    assert check_window(PointWindow(first_raw_seq=2, last_raw_seq=2, first_sample=9)).is_err


# frob:tests python/sadi/server/service.py::SessionService.capture
@pytest.mark.parametrize(
    "inputs",
    [
        {"volts": float("nan"), "height": 0.01},
        {"volts": float("inf"), "height": 0.01},
        {"volts": 1e308, "height": 0.01},
        {"volts": 0.1, "height": -0.01},
    ],
)
def test_capture_rejects_bad_inputs_and_writes_nothing(client: TestClient, inputs: Any) -> None:
    """Out-of-range or non-finite capture inputs 422 and leave the point log empty."""
    resp = _post(client, "calibration", inputs)
    assert resp.status_code == 422
    assert client.get("/api/session/points").json() == []


# frob:tests python/sadi/server/service.py::SessionService.capture
def test_capture_diameter_mm_hint(client: TestClient) -> None:
    """A specimen diameter typed in mm is refused with a unit hint."""
    resp = _post(client, "specimen", {"diameter": 0.2, "length": 0.1})
    assert resp.status_code == 422
    assert "millimetres" in resp.json()["detail"]
    assert client.get("/api/session/points").json() == []


# frob:tests python/sadi/server/service.py::SessionService.capture
@pytest.mark.parametrize(
    "window",
    [
        {"first_raw_seq": -1, "last_raw_seq": 3},
        {"first_raw_seq": 9, "last_raw_seq": 3},
    ],
)
def test_capture_rejects_bad_window(client: TestClient, window: Any) -> None:
    """Negative or reversed windows 422 and record nothing."""
    resp = _post(client, "calibration", {"volts": 0.1, "height": 0.01}, window)
    assert resp.status_code == 422
    assert resp.json()["type"].endswith("bad_window")
    assert client.get("/api/session/points").json() == []


# frob:tests python/sadi/server/service.py::SessionService.complete
def test_calibrate_needs_valid_fit(client: TestClient) -> None:
    """Calibrate cannot be completed from points that give no valid fit."""
    assert client.post("/api/session/wizard/skip", json={"step": "setup"}).status_code == 200
    for _ in range(3):
        assert _post(client, "calibration", {"volts": 0.1, "height": 0.01}).status_code == 201
    resp = client.post("/api/session/wizard/complete", json={"step": "calibrate"})
    assert resp.status_code == 422
    assert resp.json()["type"].endswith("step_quality_gate")


# frob:tests python/sadi/server/service.py::SessionService.complete
def test_setup_blocked_by_failed_clamp_check(client: TestClient) -> None:
    """A failed clamp-slip check blocks setup completion until repeated or skipped."""
    for zb, za, slips in [(0.0, 0.0, 0), (0.0, 1e-6, 0), (0.0, 5e-3, 1)]:
        inputs = {"zero_before": zb, "zero_after": za, "slip_events": slips}
        assert _post(client, "setup", inputs).status_code == 201
    resp = client.post("/api/session/wizard/complete", json={"step": "setup"})
    assert resp.status_code == 422
    assert resp.json()["type"].endswith("step_quality_gate")
    assert len(client.get("/api/session/points").json()) == 3


# frob:tests python/sadi/labs/lctt/lab.py::calibration_gate
def test_calibration_gate_unit() -> None:
    """The gate blocks too few or degenerate points and passes a real line."""
    same = [{"volts": 0.1, "height": 0.01}] * 3
    assert calibration_gate(same) is not None
    assert calibration_gate([]) is not None
    line = [{"volts": 0.1 * i, "height": 0.01 * i} for i in range(1, 5)]
    assert calibration_gate(line) is None


# frob:tests python/sadi/labs/lctt/lab.py::clamp_gate
def test_clamp_gate_unit() -> None:
    """The gate stays quiet until the verdict, blocks a failed one and passes a good one."""
    gate = clamp_gate()
    good = {"zero_before": 0.0, "zero_after": 0.0, "slip_events": 0}
    bad = {"zero_before": 0.0, "zero_after": 5e-3, "slip_events": 1}
    assert gate([good]) is None
    assert gate([good, good, bad]) is not None
    assert gate([good, good, good]) is None
