"""Launcher crash-recovery paths: stale lock flag, TIME_WAIT-safe port check, unwritable root."""

# frob:ticket 01M71Z6EMJ9QP7716699S5SC5X
from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typani import Ok

from sadi import launcher
from sadi.store.lock import LOCK_FILENAME, LockStale, acquire


class _Dev:
    """Minimal device stand-in satisfying the DeviceProbe surface."""

    status = "simulated"
    fault = None

    def close(self) -> None:
        """No-op close."""


def _enter(app: FastAPI, _host: str, _port: int) -> None:
    """Fake server: run the app lifespan like uvicorn would."""
    with TestClient(app):
        pass


def _argv(root: Path, *extra: str) -> list[str]:
    """Common launcher argv using the injected fake simulator."""
    return [
        "--sim",
        "--skip-preflight",
        "--no-browser",
        "--port",
        "0",
        "--data-root",
        str(root),
        *extra,
    ]


def test_stale_lock_message_names_the_launcher_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """frob:tests sadi.store.lock.acquire - stale hint names `sadi serve --recover-stale`."""
    monkeypatch.setattr(launcher, "open_sim_device", lambda: Ok(_Dev()))
    lockfile = tmp_path / LOCK_FILENAME
    lockfile.write_text("pid=999999 host=gone\n")
    assert isinstance(acquire(tmp_path).danger_err, LockStale)
    assert launcher.main(_argv(tmp_path), _enter) == launcher.EXIT_LOCK
    err = capsys.readouterr().err
    assert "--recover-stale" in err and "safe" in err
    assert lockfile.read_text() == "pid=999999 host=gone\n"  # refusal changes nothing


def test_recover_stale_flag_takes_over_without_touching_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frob:tests sadi.launcher.main - --recover-stale starts on a dead holder's lock."""
    monkeypatch.setattr(launcher, "open_sim_device", lambda: Ok(_Dev()))
    (tmp_path / LOCK_FILENAME).write_text("pid=999999 host=gone\n")
    keep = tmp_path / "session.keep"
    keep.write_bytes(b"precious")
    assert launcher.main(_argv(tmp_path, "--recover-stale"), _enter) == 0
    assert keep.read_bytes() == b"precious"


def test_port_check_uses_reuseaddr_for_time_wait() -> None:
    """frob:tests sadi.launcher._port_free - a port with only TIME_WAIT sockets is free."""
    if os.name == "nt":
        pytest.skip("SO_REUSEADDR is deliberately not set on Windows")
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    cli = socket.create_connection(("127.0.0.1", port))
    conn, _ = srv.accept()
    conn.close()  # server side closes first -> TIME_WAIT on the server port
    cli.close()
    srv.close()
    assert launcher._port_free("127.0.0.1", port)


def test_port_check_still_detects_live_listener() -> None:
    """frob:tests sadi.launcher._port_free - a live listener is still busy."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        assert not launcher._port_free("127.0.0.1", srv.getsockname()[1])
    finally:
        srv.close()


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions and a non-root user",
)
def test_unwritable_root_gives_plain_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """frob:tests sadi.launcher.data_root_unwritable_hint - permission denied, plain words."""
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        hint = launcher.data_root_unwritable_hint(ro / "data")
        code = launcher.main(_argv(ro / "data"), _enter)
    finally:
        ro.chmod(0o700)
    assert hint is not None and "Permission denied" in hint and "--data-root" in hint
    assert code == launcher.EXIT_LOCK
    assert "Permission denied" in capsys.readouterr().err
    assert not (ro / "data").exists()


def test_writable_root_has_no_hint(tmp_path: Path) -> None:
    """frob:tests sadi.launcher.data_root_unwritable_hint - writable or creatable is fine."""
    assert launcher.data_root_unwritable_hint(tmp_path / "new" / "deeper") is None
