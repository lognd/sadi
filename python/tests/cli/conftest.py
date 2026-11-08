"""Autouse isolation so app startup never scans the real user data or OS temp dirs."""

# frob:ticket 01M6WPBZK1AYHDYR3RSR656D8Z
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_spill_dirs(isolated_spill_dirs: tuple[Path, Path]) -> None:
    """Apply the shared spill-dir redirect to every test in this package."""
