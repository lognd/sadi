"""Real mode with no board starts disconnected: read endpoints work, capture is blocked."""

# frob:ticket 01M7242CRQGBYWTR080XEYNFS9
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typani import Err

from sadi import launcher
from sadi.server import device_open


def _argv(root: Path, *extra: str) -> list[str]:
    return ["serve", "--skip-preflight", "--no-browser", "--port", "0", "--data-root",
            str(root), *extra]


# frob:tests python/sadi/launcher.py::_serve
def test_no_board_serves_disconnected_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unopenable port: exit 0, unopened device + live, status disconnected, no session."""
    monkeypatch.setattr(device_open, "open_real_device", lambda _p: Err("board missing"))
    seen: list[dict[str, object]] = []

    def fake_serve(app: FastAPI, _h: str, _p: int) -> None:
        cfg = app.state.settings
        with TestClient(app) as client:
            view = client.get("/api/device/status").json()
        seen.append({"device": cfg.device, "live": cfg.live, "view": view})

    code = launcher.main(_argv(tmp_path, "--device-port", "/dev/ttyNOPE"), fake_serve)
    assert code == 0
    assert seen[0]["device"] is not None and seen[0]["live"] is not None
    view = seen[0]["view"]
    assert isinstance(view, dict)
    assert view["attached"] is False and view["status"] == "disconnected"
    err_out = capsys.readouterr().err
    assert "WARNING" in err_out and "board missing" in err_out and "capture is blocked" in err_out
    assert not list(tmp_path.glob("**/*.wal")) and not list(tmp_path.glob("**/*.sadi"))


# frob:tests python/sadi/launcher.py::_serve
def test_unwritable_data_root_still_exits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The no-device fallback never masks a data-root failure."""
    monkeypatch.setattr(device_open, "open_real_device", lambda _p: Err("board missing"))
    monkeypatch.setattr(launcher, "data_root_unwritable_hint", lambda _r: "read-only")
    assert launcher.main(_argv(tmp_path), lambda *_a: None) == launcher.EXIT_LOCK
