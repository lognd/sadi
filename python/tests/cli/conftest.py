"""Autouse isolation so app startup never scans the real user data or OS temp dirs."""

# frob:ticket 01M6WPBZK1AYHDYR3RSR656D8Z
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_spill_dirs(isolated_spill_dirs: tuple[Path, Path]) -> None:
    """Apply the shared spill-dir redirect to every test in this package."""


class FakeBoard:
    """Hardware-free stand-in for the opened SADI board DeviceService."""

    status = "connected"
    fault = None
    closed = False

    def close(self) -> None:
        """Record shutdown."""
        FakeBoard.closed = True


@pytest.fixture(autouse=True)
def _no_real_board(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch a real serial port: `sadi serve` without --sim opens a fake board instead."""
    from typani import Ok

    from sadi.server import device_open

    FakeBoard.closed = False
    monkeypatch.setattr(device_open, "open_real_device", lambda _port: Ok(FakeBoard()))
