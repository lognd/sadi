"""wheels.yml: structural checks (3 OS, smoke step, no auto-publish)."""

# frob:ticket 01M6W7RB48NB50QHR6VJX9JXZ4
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
TEXT = (ROOT / ".github" / "workflows" / "wheels.yml").read_text(encoding="utf-8")
WF = yaml.safe_load(TEXT)


def test_triggers() -> None:
    """Tag push and manual dispatch only."""
    on = WF[True]  # YAML 1.1 parses the key `on` as True
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"]["tags"]


def test_matrix_covers_three_os() -> None:
    """Wheel build and smoke jobs cover linux, windows and macos."""
    wheels = {i["os"] for i in WF["jobs"]["sadi-py-wheels"]["strategy"]["matrix"]["include"]}
    smoke = set(WF["jobs"]["smoke"]["strategy"]["matrix"]["os"])
    for oses in (wheels, smoke):
        for fam in ("ubuntu", "windows", "macos"):
            assert any(o.startswith(fam) for o in oses), fam


def test_smoke_runs_version_and_selftest() -> None:
    """The smoke job runs both commands from a venv."""
    run = "\n".join(s.get("run", "") for s in WF["jobs"]["smoke"]["steps"])
    assert "venv" in run and "--version" in run and "--selftest" in run


def test_no_auto_publish() -> None:
    """Nothing uploads to PyPI."""
    low = TEXT.lower()
    for bad in ("pypi-publish", "twine", "maturin publish", "maturin upload"):
        assert bad not in low
    assert "id-token" not in low


def test_release_doc_states_unverified() -> None:
    """docs/release.md documents the procedure and marks the workflow UNVERIFIED."""
    doc = (ROOT / "docs" / "release.md").read_text(encoding="utf-8")
    assert "Status: current" in doc and "UNVERIFIED" in doc and "Procedure" in doc
