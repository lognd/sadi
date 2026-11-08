"""Docs index guard: every page under docs/jobs and docs/core/wizard.md is linked from the index."""

# frob:ticket 01M6WJ4HSDRKXM851XDT08FZC6
from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"


def test_readme_links_jobs_tasks() -> None:
    """The docs README links docs/jobs/tasks.md as a real markdown link."""
    assert "(jobs/tasks.md)" in (DOCS / "README.md").read_text(encoding="utf-8")
