"""Provenance reaches the store, API, export, plots, results and ws; the real path is unchanged."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from sadi.core.pipeline import Bus
from sadi.server.app import AppSettings, create_app
from sadi.store.manifest import read_manifest
from sadi.store.session import SYNTHETIC_MARKER, ProvenanceMismatch, session_is_synthetic
from sadi.synthetic.driver import drive_lab
from sadi.synthetic.provenance import CONFIRM_PHRASE, EXPORT_PREFIX, PROVENANCE_HEADER
from sadi.synthetic.scenario import generate_scenario

Make = Callable[..., TestClient]


def _create(c: TestClient) -> dict[str, object]:
    res = c.post("/api/sessions", json={"lab": "lctt", "slug": "t"})
    assert res.status_code == 201, res.text
    return res.json()


# frob:tests python/sadi/store/session.py::session_is_synthetic
# frob:tests python/sadi/server/service.py::SessionService.create
def test_synthetic_session_is_marked_in_store_and_api(make_client: Make, tmp_path: Path) -> None:
    """Marker file, manifest mirror and session info all say synthetic."""
    c = make_client(synthetic=True)
    info = _create(c)
    d = tmp_path / "sessions" / str(info["name"])
    assert (d / SYNTHETIC_MARKER).is_file() and session_is_synthetic(d)
    assert read_manifest(d).danger_ok.synthetic is True
    assert info["provenance"]["synthetic"] is True
    assert c.get("/api/session").json()["provenance"]["synthetic"] is True
    listed = c.get("/api/sessions").json()
    assert listed[0]["provenance"]["synthetic"] is True


# frob:tests python/sadi/server/service.py::SessionService.provenance
def test_real_path_is_unaffected(make_client: Make, tmp_path: Path) -> None:
    """A default app writes no marker and reports real provenance everywhere."""
    c = make_client()
    info = _create(c)
    d = tmp_path / "sessions" / str(info["name"])
    assert not (d / SYNTHETIC_MARKER).exists() and not session_is_synthetic(d)
    assert read_manifest(d).danger_ok.synthetic is False
    assert info["provenance"]["synthetic"] is False
    assert c.get("/api/health").json()["provenance"]["synthetic"] is False
    assert c.get("/api/plots/calibration").json()["provenance"]["synthetic"] is False


# frob:tests python/sadi/store/session.py::resume_session
def test_resume_inherits_and_refuses_mode_mix(make_client: Make, tmp_path: Path) -> None:
    """A synthetic parent resumes synthetic; a real server refuses it (409), and vice versa."""
    c = make_client(synthetic=True)
    first = _create(c)
    c.post("/api/session/close")
    ok = c.post("/api/sessions/resume", json={"name": first["name"]})
    assert ok.status_code == 201 and ok.json()["provenance"]["synthetic"] is True
    c.post("/api/session/close")
    child = tmp_path / "sessions" / ok.json()["name"]
    assert session_is_synthetic(child)
    c.__exit__(None, None, None)
    real = make_client()
    bad = real.post("/api/sessions/resume", json={"name": first["name"]})
    assert bad.status_code == 409, bad.text
    assert ProvenanceMismatch.__name__ in bad.text


# frob:tests python/sadi/server/routes/export.py::render_export
# frob:tests python/sadi/synthetic/provenance.py::stamp_export
def test_every_export_is_branded_synthetic(make_client: Make) -> None:
    """Filenames, bodies and headers of synthetic exports carry the provenance."""
    c = make_client(synthetic=True)
    res = drive_lab(c, generate_scenario(5))
    assert res.is_ok, res
    fmts = c.get("/api/export").json()
    assert fmts
    for f in fmts:
        r = c.get(f"/api/export/{f['id']}")
        assert r.status_code == 200
        assert r.headers[PROVENANCE_HEADER] == "synthetic"
        if f["download"]:
            assert EXPORT_PREFIX in r.headers["content-disposition"]
            assert b"SYNTHETIC" in r.content[:400]
        elif f["media_type"] == "application/json":
            body = json.loads(r.content)
            assert body["provenance"]["synthetic"] is True


# frob:tests python/sadi/server/routes/export.py::render_export
def test_real_exports_are_unbranded(make_client: Make) -> None:
    """Real exports keep their plain names and carry a 'real' header only."""
    c = make_client()
    _create(c)
    for f in c.get("/api/export").json():
        r = c.get(f"/api/export/{f['id']}")
        if r.status_code != 200:
            continue
        assert r.headers[PROVENANCE_HEADER] == "real"
        assert EXPORT_PREFIX not in r.headers.get("content-disposition", "")
        assert b"SYNTHETIC" not in r.content[:200]


# frob:tests python/sadi/server/routes/plots.py::make_plots_router
# frob:tests python/sadi/server/routes/results.py::live_results
def test_plots_results_health_ws_carry_provenance(make_client: Make) -> None:
    """Plot, results, health and the ws hello all say synthetic."""
    c = make_client(synthetic=True)
    _create(c)
    assert c.get("/api/health").json()["provenance"]["synthetic"] is True
    assert c.get("/api/plots/calibration").json()["provenance"]["synthetic"] is True
    assert c.get("/api/plots/stress-strain").json()["provenance"]["synthetic"] is True
    assert c.get("/api/results").json()["data_provenance"]["synthetic"] is True


# frob:tests python/sadi/server/ws.py::StreamHub
def test_ws_hello_carries_provenance(tmp_path: Path) -> None:
    """The ws hello message states the data mode."""
    for synthetic in (True, False):
        app = create_app(
            AppSettings(data_root=tmp_path, bus=Bus(), require_root_lock=False, synthetic=synthetic)
        )
        with TestClient(app) as c, c.websocket_connect("/api/stream") as ws:
            hello = ws.receive_json()
        assert hello["provenance"]["synthetic"] is synthetic


def test_phrase_constant_is_loud() -> None:
    """The confirmation phrase says the data is simulated."""
    assert "SIMULATED" in CONFIRM_PHRASE
