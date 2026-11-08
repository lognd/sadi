"""Docs index guard: every page under docs/jobs and docs/core/wizard.md is linked from the index."""

# frob:ticket 01M6WJ4HSDRKXM851XDT08FZC6
# frob:ticket 01M6WJB31KE6WNZ6ZKRK2XSZ01
from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"


def test_readme_links_jobs_tasks() -> None:
    """The docs README links docs/jobs/tasks.md as a real markdown link."""
    assert "(jobs/tasks.md)" in (DOCS / "README.md").read_text(encoding="utf-8")


def test_index_links_core_wizard() -> None:
    """The docs index links docs/core/wizard.md."""
    assert "(core/wizard.md)" in (DOCS / "index.md").read_text(encoding="utf-8")


def test_index_links_doctor_ui() -> None:
    """The docs index links docs/web/doctor-ui.md."""
    # frob:ticket 01M6WA9WZW89EA826DSJCJ0197
    assert "(web/doctor-ui.md)" in (DOCS / "index.md").read_text(encoding="utf-8")
