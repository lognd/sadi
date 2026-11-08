"""Plot-data routes over the real app: calibration scatter+fit, stress-strain, problems."""

# frob:ticket 01M6WWN92GG11X653PP544SRDC

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.store.events import PointV1, PointWindow, point_record
from sadi.store.session import SessionMeta, create_session_in_held_root
from sadi.store.writer_thread import WriterHandle

WINDOW = {"first_raw_seq": 1, "last_raw_seq": 5}
K = 1.0e-3  # m per volt


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with the lctt lab over a tmp data root."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        yield c


def _post(c: TestClient, phase: str, **inputs: float) -> None:
    body: dict[str, Any] = {"phase": phase, "inputs": inputs, "window": WINDOW}
    res = c.post("/api/session/points", json=body)
    assert res.status_code == 201, res.text


def _open(c: TestClient) -> None:
    assert c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).status_code == 201
    assert c.post("/api/session/wizard/skip", json={"step": "setup"}).status_code == 200


# frob:tests python/sadi/server/routes/plots.py::make_plots_router
def test_no_session_is_problem(client: TestClient) -> None:
    """Without an open session both endpoints are 409 problem+json with a hint."""
    for url in ("/api/plots/calibration", "/api/plots/stress-strain"):
        res = client.get(url)
        assert res.status_code == 409
        assert res.headers["content-type"].startswith("application/problem+json")
        assert res.json()["hint"]


# frob:tests python/sadi/server/routes/plots.py::calibration_plot
def test_calibration_points_without_and_with_fit(client: TestClient) -> None:
    """Fewer than 3 points give a scatter with no fit; 5 give slope, intercept and a band."""
    _open(client)
    for v in range(2):
        _post(client, "calibration", volts=float(v), height=0.08 + K * v)
    few = client.get("/api/plots/calibration").json()
    assert few["volts"] == [0.0, 1.0] and few["fit"] is None
    for v in range(2, 5):
        _post(client, "calibration", volts=float(v), height=0.08 + K * v)
    got = client.get("/api/plots/calibration").json()
    assert got["volts"] == [float(v) for v in range(5)]
    fit = got["fit"]
    assert fit["n"] == 5
    assert fit["slope_m_per_v"] == pytest.approx(K)
    assert fit["intercept_m"] == pytest.approx(0.08)
    assert len(fit["band_volts"]) == len(fit["band_half_width_m"]) == 5


def _record(root: Path, slug: str, with_loads: bool) -> str:
    """Write a closed session (cal, tare, specimen, optional loads); return its name."""
    h = create_session_in_held_root(root, SessionMeta(slug=slug, lab_module="lctt")).danger_ok
    w = WriterHandle.open(h.path / "wal", uuid.uuid4(), 1).danger_ok

    def pt(phase: str, **inputs: float) -> None:
        p = PointV1(phase=phase, window=PointWindow(first_raw_seq=1, last_raw_seq=1), inputs=inputs)
        assert w.submit(point_record(p)).is_ok

    for v in range(5):
        pt("calibration", volts=float(v), height=0.08 + K * v)
    if with_loads:
        pt("tare", mean=0.0, sd=0.001, n=100)
        pt("specimen", diameter=0.005, u_diameter=1e-6, hanger_kg=0.1)
        for i in range(4):
            pt("load", volts=0.01 * (i + 1), mass_kg=float(i + 1))
    assert w.close().is_ok
    assert h.close().is_ok
    return h.path.name


# frob:tests python/sadi/server/routes/plots.py::stress_strain_plot
def test_stress_strain_empty_then_points_and_exclusion(tmp_path: Path) -> None:
    """Empty until specimen+tare exist; then one row per load point, excluded flagged; read-only."""
    bare = _record(tmp_path, "bare", with_loads=False)
    full = _record(tmp_path, "full", with_loads=True)
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as client:
        _exercise(client, tmp_path, bare, full)


def _exercise(client: TestClient, tmp_path: Path, bare: str, full: str) -> None:
    """Resume the bare then the full session and check the stress-strain payloads."""
    assert client.post("/api/sessions/resume", json={"name": bare}).status_code == 201
    empty = client.get("/api/plots/stress-strain").json()
    assert empty["strain"] == [] and empty["excluded"] == []
    client.post("/api/session/close")
    assert client.post("/api/sessions/resume", json={"name": full}).status_code == 201

    def snap() -> dict[str, bytes]:
        return {
            str(p): p.read_bytes()
            for p in tmp_path.rglob("*")
            if p.is_file() and p.suffix != ".lock"
        }

    before = snap()
    got = client.get("/api/plots/stress-strain").json()
    assert len(got["strain"]) == len(got["stress_mpa"]) == len(got["point_ids"]) == 4
    assert got["excluded"] == [False] * 4
    assert got["stress_mpa"][-1] > got["stress_mpa"][0] > 0
    assert snap() == before
    pts = client.get("/api/session/points").json()
    target = pts[-1]["point_id"]
    edit = client.post(f"/api/session/points/{target}/edit", json={"op": "exclude", "args": {}})
    assert edit.status_code == 200, edit.text
    assert client.get("/api/plots/stress-strain").json()["excluded"].count(True) == 1
