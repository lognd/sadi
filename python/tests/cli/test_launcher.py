"""Tests for the `sadi` launcher."""

# frob:ticket 01M6WMGMM1BP37GS27VRRX9AYP
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typani import Err, Ok

from sadi import launcher
from sadi.store.lock import acquire


def _ok(*_a: object) -> object:
    return Ok(None)


def _enter(app: FastAPI, _host: str, _port: int) -> None:
    """Fake server: run the app lifespan like uvicorn would."""
    with TestClient(app):
        pass


def test_mount_web_serves_index(tmp_path: Path) -> None:
    """frob:tests sadi.launcher.mount_web"""
    (tmp_path / "index.html").write_text("<html>hi</html>")
    app = FastAPI()
    assert launcher.mount_web(app, tmp_path)
    assert "hi" in TestClient(app).get("/").text


def test_mount_web_absent(tmp_path: Path) -> None:
    """Missing dist is not an error; nothing is mounted."""
    assert not launcher.mount_web(FastAPI(), tmp_path / "nope")


def test_serve_default_host_and_lock_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frob:tests sadi.launcher.main - bare `sadi` serves on 127.0.0.1 and exits 0."""
    monkeypatch.setattr(launcher, "preflight", _ok)
    seen: list[tuple[str, int]] = []

    def serve(app: FastAPI, host: str, port: int) -> None:
        seen.append((host, port))
        _enter(app, host, port)

    assert launcher.main(["--data-root", str(tmp_path)], serve) == 0
    assert seen == [("127.0.0.1", 8000)]


def test_refused_lock_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A live lock is never stolen; the launcher exits non-zero with the hint."""
    monkeypatch.setattr(launcher, "preflight", _ok)
    held = acquire(tmp_path, recover_stale=False)
    assert held.is_ok
    try:
        code = launcher.main(["serve", "--data-root", str(tmp_path)], _enter)
    finally:
        held.danger_ok.release()
    assert code == launcher.EXIT_LOCK
    assert "cannot lock data root" in capsys.readouterr().err


def test_preflight_failure_blocks_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A doctor blocker prints its report and the server is never started."""
    monkeypatch.setattr(launcher, "preflight", lambda *_a: Err("STEP 1: fix it\n"))
    called: list[int] = []

    def serve(_a: FastAPI, _h: str, _p: int) -> None:
        called.append(1)

    code = launcher.main(["serve", "--data-root", str(tmp_path)], serve)
    assert code == launcher.EXIT_PREFLIGHT
    assert not called
    assert "STEP 1: fix it" in capsys.readouterr().err


def test_doctor_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """`sadi doctor ...` forwards its arguments to the doctor CLI."""
    got: list[list[str]] = []

    def fake(argv: list[str]) -> int:
        got.append(argv)
        return 0

    monkeypatch.setattr(launcher, "doctor_main", fake)
    assert launcher.main(["doctor", "list"]) == 0
    assert got == [["list"]]


def test_preflight_blocker_is_err(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """frob:tests sadi.launcher.preflight"""
    monkeypatch.setattr(launcher, "exit_code", lambda _r: 2)
    monkeypatch.setattr(launcher, "render", lambda _r: "REPORT")
    monkeypatch.setattr(launcher, "run", lambda _o: Ok(object()))
    got = launcher.preflight(tmp_path, 8000)
    assert got.is_err
    assert got.danger_err == "REPORT"
