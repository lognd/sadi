"""A capture retried with the same request_id returns the first commit and records once."""

# frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
# creates:python/tests/server/test_capture_request_id.py

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.schemas import CaptureBody, SessionCreate
from sadi.server.service import SessionService

WINDOW = {"first_raw_seq": 1, "last_raw_seq": 5}


@pytest.fixture
def svc(tmp_path: Path) -> Iterator[SessionService]:
    """Service over `root` with lctt registered and a session open past setup."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    svc = SessionService(tmp_path, labs)
    assert svc.create(SessionCreate(lab="lctt", slug="rq")).is_ok
    assert svc.skip("setup").is_ok
    yield svc
    assert svc.close().is_ok


def _body(rid: str | None) -> CaptureBody:
    """A calibration capture body carrying `rid`."""
    return CaptureBody.model_validate(
        {
            "phase": "calibration",
            "inputs": {"volts": 1.0, "height": 0.01},
            "window": WINDOW,
            "request_id": rid,
        }
    )


def _count(svc: SessionService) -> int:
    """Count points via the replayed view."""
    cur = svc._open  # noqa: SLF001
    assert cur is not None
    return len(svc._replay(cur).danger_ok.view().points)  # noqa: SLF001


# frob:tests python/sadi/server/service.py::SessionService.capture
def test_replayed_request_id_returns_same_seq_and_records_once(svc: SessionService) -> None:
    """The retry gets the original seq; only one POINT exists."""
    first = svc.capture(_body("abc")).danger_ok
    again = svc.capture(_body("abc")).danger_ok
    assert again.seq == first.seq
    assert _count(svc) == 1


# frob:tests python/sadi/server/service.py::SessionService._existing_capture
def test_distinct_and_absent_request_ids_each_record(svc: SessionService) -> None:
    """Different ids, and no id, are separate captures."""
    assert svc.capture(_body("a")).is_ok
    assert svc.capture(_body("b")).is_ok
    assert svc.capture(_body(None)).is_ok
    assert _count(svc) == 3


# frob:tests python/sadi/server/service.py::SessionService._existing_capture
def test_replay_after_reopen_finds_point_in_log(svc: SessionService) -> None:
    """The id is persisted in the POINT, so it survives without the in-memory map."""
    first = svc.capture(_body("zz")).danger_ok
    cur = svc._open  # noqa: SLF001
    assert cur is not None
    cur.requests.clear()
    assert svc.capture(_body("zz")).danger_ok.seq == first.seq
    assert _count(svc) == 1
