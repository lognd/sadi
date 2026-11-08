"""Packaging guard: pyproject declares the optional 'device' extra for sadi_py."""

# frob:ticket 01M6WP9HGP60JCXMHC1E6E3EVV
from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_device_extra_declared() -> None:
    """python/pyproject.toml declares a 'device' optional-dependencies extra."""
    # frob:tests test_device_extra_declared
    data = tomllib.loads((ROOT / "python" / "pyproject.toml").read_text(encoding="utf-8"))
    assert "device" in data["project"]["optional-dependencies"]


def test_packaging_doc_linked() -> None:
    """docs/packaging.md has a Status header and is linked from the docs index."""
    text = (ROOT / "docs" / "packaging.md").read_text(encoding="utf-8")
    assert "Status:" in text
    assert "(packaging.md)" in (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
