"""DATA-010 tells a permission problem from a missing folder (audit1 #40)."""

# frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5
from __future__ import annotations

from doctor_fakes import FakeProbes, healthy

import sadi.doctor as doctor
from sadi.doctor.schema import RunOptions, Status


def _headline(p: FakeProbes) -> tuple[Status, str]:
    got = doctor.run(RunOptions(checks=("DATA-010",)), p).unwrap().results[0]
    return got.status, got.headline


# frob:tests python/sadi/doctor/checks/data.py::data_010
def test_missing_root_with_writable_parent_is_missing() -> None:
    p = healthy()
    p.dirs.pop(p.data_dir)
    status, headline = _headline(p)
    assert status is Status.FAIL
    assert "does not exist" in headline


# frob:tests python/sadi/doctor/checks/data.py::data_010
def test_missing_root_under_unwritable_parent_says_permission_denied() -> None:
    p = healthy()
    p.dirs.pop(p.data_dir)
    p.dirs["/home/u/.local/share"] = []
    p.read_only.add("/home/u/.local/share")
    status, headline = _headline(p)
    assert status is Status.FAIL
    assert "Permission denied" in headline
