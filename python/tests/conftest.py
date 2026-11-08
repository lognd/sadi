"""Shared pytest fixtures for the SADI Python suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_session_dir(tmp_path: Path) -> Path:
    """Return an empty scratch directory for tests that need a session root."""
    root = tmp_path / "sessions"
    root.mkdir()
    return root
