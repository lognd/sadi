"""Shared pytest fixtures for the SADI Python suite."""

from __future__ import annotations

# frob:ticket 01M6WPBZK1AYHDYR3RSR656D8Z
from pathlib import Path

import pytest

from sadi.store.spill import user_data_dir


@pytest.fixture
def tmp_session_dir(tmp_path: Path) -> Path:
    """Return an empty scratch directory for tests that need a session root."""
    root = tmp_path / "sessions"
    root.mkdir()
    return root


@pytest.fixture
def isolated_spill_dirs(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Redirect user-data and OS temp dirs to empty tmp dirs; return (user_dir, temp_dir)."""
    home = tmp_path_factory.mktemp("isolated-home")
    xdg = home / "xdg"
    temp = home / "tmp"
    temp.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "local"))
    monkeypatch.setattr("tempfile.tempdir", str(temp))
    return user_data_dir(), temp


# frob:ticket 01M72VM5ZCW15RQ2CH8RS7XR3X
@pytest.fixture(autouse=True)
def _autouse_isolated_spill_dirs(isolated_spill_dirs: tuple[Path, Path]) -> None:
    """Isolate the user-data and OS temp spill dirs for every test (audit7 M5)."""
