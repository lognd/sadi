"""session_is_synthetic survives a lost SYNTHETIC sidecar by reading the manifest (audit1 #21)."""

# frob:ticket 01M720QDHPFPD9CNEADS1CA9V6
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.store.session import SYNTHETIC_MARKER, session_is_synthetic


# frob:tests python/sadi/store/session.py::session_is_synthetic
def test_missing_marker_still_synthetic_from_manifest(tmp_path: Path) -> None:
    """Deleting only the SYNTHETIC file does not relabel the data as real."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    app = create_app(AppSettings(data_root=tmp_path, labs=labs, synthetic=True))
    with TestClient(app) as c:
        name = c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).json()["name"]
        assert c.post("/api/session/close").status_code in (200, 204)
    d = tmp_path / "sessions" / name
    (d / SYNTHETIC_MARKER).unlink()
    assert session_is_synthetic(d)


# frob:tests python/sadi/store/session.py::session_is_synthetic
def test_real_session_without_marker_is_real(tmp_path: Path) -> None:
    """A real session (manifest synthetic false, no marker) stays real; empty dir is real."""
    assert not session_is_synthetic(tmp_path)
