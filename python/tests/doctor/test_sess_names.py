"""Tests for the SESS check fact helper `names`."""

# frob:ticket 01M6WT0G5WYA0P635SERVMGEGS
from __future__ import annotations

from sadi.doctor.checks.sess import names
from sadi.doctor.sessions import SessionFacts


# frob:tests python/sadi/doctor/checks/sess.py::names
def test_names_lists_sessions_and_paths() -> None:
    """names returns parallel session-name and path lists, empty for no rows."""
    rows = [
        SessionFacts(name="a_v1", path="/r/sessions/a_v1", name_ok=True),
        SessionFacts(name="b", path="/r/sessions/b", name_ok=False),
    ]
    assert names(rows) == {
        "sessions": ["a_v1", "b"],
        "paths": ["/r/sessions/a_v1", "/r/sessions/b"],
    }
    assert names([]) == {"sessions": [], "paths": []}
