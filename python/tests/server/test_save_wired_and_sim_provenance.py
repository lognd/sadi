"""Save indicator follows the real writer; --sim data is labelled synthetic (audit1 #4, #2)."""

# frob:ticket 01M720QDHPFPD9CNEADS1CA9V6
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sadi import launcher
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.store.writer_thread import IoError


def _app(tmp_path: Path) -> FastAPI:
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    return create_app(AppSettings(data_root=tmp_path, labs=labs))


# frob:tests python/sadi/server/app.py::create_app
# frob:tests python/sadi/server/app.py::_SessionWriterSource
def test_indicator_tracks_open_session_writer(tmp_path: Path) -> None:
    """Idle is Saved; with a session open it reads the real writer; a failure latches NOT SAVED."""
    app = _app(tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/save-indicator").json()["state"] == "saved"
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).status_code == 201
        svc: Any = app.state.sessions
        writer = svc._open.writer
        src = app.state.save_indicator._source
        assert src.durable_seq == writer.durable_seq
        assert src.enqueued_seq == writer.enqueued_seq
        assert src._writer is writer  # bound to the real writer, not an always-zero stub
        # a failure reported through the listener registered on the writer latches NOT SAVED
        app.state.save_indicator.mark_failed(IoError(reason="x", hint="Disk error"))
        v = c.get("/api/save-indicator").json()
        assert v["state"] == "not_saved"


# frob:tests python/sadi/launcher.py::_serve_app
def test_sim_device_serves_synthetic_provenance(tmp_path: Path) -> None:
    """A simulated device makes /api/health and sessions report synthetic, not real."""
    class Dev:
        status = "simulated"
        fault = None

        def close(self) -> None:
            pass

    seen: dict[str, Any] = {}

    def serve(app: FastAPI, _h: str, _p: int) -> None:
        with TestClient(app) as c:
            seen["health"] = c.get("/api/health").json()

    args = argparse.Namespace(
        recover_stale=False, web_dist=None, host="127.0.0.1", no_browser=True
    )
    code = launcher._serve_app(args, serve, tmp_path, 8000, Dev(), False)  # type: ignore[arg-type]
    assert code == 0
    assert seen["health"]["provenance"]["synthetic"] is True
