"""`sadi serve` without --sim opens the real SADI over serial; a missing board is explained."""

# frob:ticket 01M71WYR7EH67QFSRH37QFCDAC
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from typani import Err, Ok

from sadi import launcher
from sadi.core.device import DeviceService
from sadi.core.errors import DeviceCode, DeviceError
from sadi.server import device_open

_REAL_OPEN = device_open.open_real_device


class FakeBoard:
    """Hardware-free stand-in for the opened board."""

    status = "connected"
    fault = None

    def close(self) -> None:
        """No-op shutdown."""


def _argv(tmp_path: Path, *extra: str) -> list[str]:
    return ["serve", "--skip-preflight", "--no-browser", "--port", "0", "--data-root",
            str(tmp_path), *extra]


# frob:tests python/sadi/server/device_open.py::resolve_device_port
def test_port_resolution_flag_env_default() -> None:
    """The flag beats SADI_PORT, which beats the /dev/ttyUSB0 default."""
    assert device_open.resolve_device_port("/dev/x", {"SADI_PORT": "/dev/y"}) == "/dev/x"
    assert device_open.resolve_device_port(None, {"SADI_PORT": "/dev/y"}) == "/dev/y"
    assert device_open.resolve_device_port(None, {}) == "/dev/ttyUSB0"


# frob:tests python/sadi/launcher.py::_serve
def test_default_serve_opens_real_board_and_passes_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no source flag the launcher opens the board on the chosen port and injects it."""
    ports: list[str | None] = []
    seen: list[object] = []

    def fake_open(port: str | None) -> Ok[FakeBoard]:
        ports.append(port)
        return Ok(FakeBoard())

    monkeypatch.setattr(device_open, "open_real_device", fake_open)
    monkeypatch.delenv("SADI_PORT", raising=False)

    def fake_serve(app: FastAPI, _h: str, _p: int) -> None:
        seen.append(app.state.settings.device)

    assert launcher.main(_argv(tmp_path, "--device-port", "/dev/ttyFAKE"), fake_serve) == 0
    assert ports == ["/dev/ttyFAKE"]
    assert isinstance(seen[0], FakeBoard)


# frob:tests python/sadi/server/device_open.py::open_real_device
def test_missing_board_warns_and_serves_without_device(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A board that cannot be opened prints a plain 'plug it in' warning and still serves."""
    monkeypatch.setattr(device_open, "open_real_device", _REAL_OPEN)  # run the real opener
    err = DeviceError(code=DeviceCode.NOT_FOUND, detail="no such port")
    monkeypatch.setattr("sadi.core.device.open_serial", lambda _p, _c: Err(err))
    served: list[object] = []
    code = launcher.main(_argv(tmp_path, "--device-port", "/dev/ttyNOPE"),
                         lambda app, _h, _p: served.append(app.state.settings.device))
    assert code == 0
    assert served == [None]
    out = capsys.readouterr().err
    assert "WARNING" in out and "/dev/ttyNOPE" in out and "Plug in the SADI board" in out


# frob:tests python/sadi/server/device_open.py::open_real_device
def test_open_real_device_returns_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """open_real_device wraps a successful serial open in a DeviceService."""
    monkeypatch.setattr(DeviceService, "open", lambda self: Ok(None))
    got = _REAL_OPEN("/dev/ttyFAKE")
    assert isinstance(got.danger_ok, DeviceService)


# frob:tests python/sadi/server/device_open.py::describe_open_failure
def test_describe_open_failure_names_port_and_hint() -> None:
    """The message names the port, the cause and the board hint."""
    err = DeviceError(code=DeviceCode.PERMISSION_DENIED, detail="EACCES")
    text = device_open.describe_open_failure(err, "/dev/ttyUSB0")
    assert "/dev/ttyUSB0" in text and "EACCES" in text and "dialout" in text
