"""The launcher wires a live acquisition bus so `/api/stream` yields frames in sim mode."""

# frob:ticket 01M6X12VGS7NHWM3EZWF4YK7XN
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sadi import launcher
from sadi.store.records import RecordType
from sadi.store.wal import WalReader

pytest.importorskip("sadi_py")


# frob:tests python/sadi/launcher.py::_serve
# frob:tests python/sadi/server/live.py::LiveAcquisition.on_session_open
# frob:tests python/sadi/server/live.py::LiveAcquisition.on_session_close
# frob:tests python/sadi/server/live.py::LiveAcquisition.fault
# frob:tests python/sadi/server/live.py::LiveAcquisition.running
def test_sim_launcher_streams_frames_and_saves_raw(tmp_path: Path) -> None:
    """With --sim the stream mounts, trace frames arrive and raw blocks reach the session WAL."""

    def serve(app: FastAPI, _h: str, _p: int) -> None:
        with TestClient(app) as client:
            made = client.post("/api/sessions", json={"lab": "lctt", "slug": "live"})
            assert made.status_code == 201, made.text
            frames = 0
            with client.websocket_connect("/api/stream") as ws:
                assert json.loads(ws.receive_text())["kind"] == "hello"
                deadline = time.monotonic() + 15
                while frames == 0 and time.monotonic() < deadline:
                    msg = ws.receive()
                    if msg.get("bytes"):
                        frames += 1
            assert frames > 0
            live = app.state.sessions._on_open.__self__
            assert live.running
            assert live.fault is None
            assert client.post("/api/session/close").status_code == 204
            assert not live.running

    argv = [
        "serve",
        "--sim",
        "--skip-preflight",
        "--no-browser",
        "--port",
        "0",
        "--data-root",
        str(tmp_path),
    ]
    assert launcher.main(argv, serve=serve) == 0
    session = next((tmp_path / "sessions").iterdir())
    recs = [r.danger_ok for r in WalReader(session / "wal").records() if r.is_ok]
    assert any(r.type == int(RecordType.RAW_BLOCK) for r in recs)
