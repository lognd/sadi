"""Regression: entry modules a spawned worker re-imports must not load sadi.store."""

# frob:ticket 01M6Z0YSS14WN7XTDKQV9DETGJ
from __future__ import annotations

import subprocess
import sys

import pytest

_PROBE = (
    "import sys, importlib; importlib.import_module(sys.argv[1]); "
    "sys.exit(1 if any(m == 'sadi.store' or m.startswith('sadi.store.') for m in sys.modules) else 0)"
)


@pytest.mark.parametrize("module", ["sadi.launcher", "sadi.doctor.cli"])
def test_entry_module_does_not_import_store(module: str) -> None:
    """frob:tests sadi.launcher.main - WRK-010: importing the entry point leaves sadi.store unloaded."""
    done = subprocess.run([sys.executable, "-c", _PROBE, module], check=False)
    assert done.returncode == 0, f"{module} imports sadi.store"
