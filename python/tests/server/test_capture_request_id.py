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
from sadi.server.service import SessionService, _capture_digest  # noqa: PLC2701

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


def _body2(
    rid: str, volts: float, height: float = 0.01, window: dict[str, int] = WINDOW
) -> CaptureBody:
    """A calibration capture body with `rid`, the given live volts, gauge height and window."""
    return CaptureBody.model_validate(
        {
            "phase": "calibration",
            "inputs": {"volts": volts, "height": height},
            "window": window,
            "request_id": rid,
        }
    )


# frob:ticket 01M72T4R1WNQRV303D0WJXW1MW
# frob:tests python/sadi/server/service.py::SessionService.capture
def test_same_request_id_different_body_is_409_and_records_nothing(svc: SessionService) -> None:
    """A reused id with other inputs is refused; the first point stays, none is dropped."""
    assert svc.capture(_body2("x", 1.0)).is_ok
    bad = svc.capture(_body2("x", 1.0, height=0.02))
    assert bad.is_err
    assert bad.danger_err.status == 409
    assert "different point" in bad.danger_err.detail
    assert _count(svc) == 1


# frob:ticket 01M72VM5RSJM7EMREPXDYDN79W
# frob:tests python/sadi/server/service.py::_capture_digest
def test_retry_with_different_live_volts_and_window_is_already_saved(svc: SessionService) -> None:
    """A real retry re-reads live volts and the window; it must replay, never save twice."""
    first = svc.capture(
        _body2("r", 0.05012, window={"first_raw_seq": 1, "last_raw_seq": 5})
    ).danger_ok
    again = svc.capture(
        _body2("r", 0.05009, window={"first_raw_seq": 11, "last_raw_seq": 15})
    ).danger_ok
    assert again.seq == first.seq
    assert "Already saved" in again.summary
    assert _count(svc) == 1


# frob:tests python/sadi/server/service.py::SessionService._act
def test_act_rechecks_request_id_under_lock(svc: SessionService) -> None:
    """Even if the pre-check is skipped, _act returns the existing commit instead of writing."""
    body = _body2("y", 1.0)
    first = svc.capture(body).danger_ok
    again = svc._act(  # noqa: SLF001
        lambda _c, _r: pytest.fail("must not run"),
        request_id="y",
        digest=_capture_digest(body),
    ).danger_ok
    assert again.seq == first.seq
    assert "Already saved" in again.summary
    assert _count(svc) == 1


# frob:ticket 01M72VV7AGMWE3JE4MZFA8P5T6
# frob:tests python/sadi/server/service.py::SessionService._check_stored_digest
def test_reopened_reuse_of_id_with_different_body_is_409(svc: SessionService) -> None:
    """With the in-memory map gone, the stored digest still refuses a different point."""
    assert svc.capture(_body("fb")).is_ok
    cur = svc._open  # noqa: SLF001
    assert cur is not None
    cur.requests.clear()
    other = CaptureBody.model_validate(
        {
            "phase": "calibration",
            "inputs": {"volts": 1.0, "height": 0.02},
            "window": WINDOW,
            "request_id": "fb",
        }
    )
    err = svc.capture(other).danger_err
    assert err.status == 409
    assert "request_id_reused" in err.type
    assert _count(svc) == 1


# frob:tests python/sadi/server/service.py::SessionService._check_stored_digest
def test_stored_point_without_digest_is_a_match(svc: SessionService) -> None:
    """An older stored point (no digest) replays instead of 409."""
    first = svc.capture(_body("old")).danger_ok
    cur = svc._open  # noqa: SLF001
    assert cur is not None
    cur.requests.clear()
    assert SessionService._check_stored_digest("old", None, "x").is_ok  # noqa: SLF001
    assert svc.capture(_body("old")).danger_ok.seq == first.seq
