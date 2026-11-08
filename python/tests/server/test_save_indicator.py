"""Tests for the save indicator state machine and route."""

# frob:ticket 01M6WJT06TWZW314324QF0DHB3
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sadi.api.save_indicator import (
    SAVING_VISIBLE_WITHIN_MS,
    SaveIndicator,
    SaveState,
    make_save_indicator_router,
)
from sadi.store.writer_thread import IoError


class _Src:
    def __init__(self) -> None:
        self.durable_seq = 0
        self.enqueued_seq = 0


def _ind(src: _Src) -> SaveIndicator:
    return SaveIndicator(src, clock=lambda: 0.0, fmt_time=lambda t: "12:04:11")


# frob:tests python/sadi/api/save_indicator.py::SaveIndicator
# frob:tests python/sadi/api/save_indicator.py::SaveIndicator.__init__
# frob:tests python/sadi/api/save_indicator.py::SaveIndicator.view
# frob:tests python/sadi/api/save_indicator.py::SeqSource.durable_seq
# frob:tests python/sadi/api/save_indicator.py::SeqSource.enqueued_seq
def test_idle_is_saved() -> None:
    v = _ind(_Src()).view()
    assert v.state is SaveState.SAVED
    assert v.label == "Saved 12:04:11"


# frob:tests python/sadi/api/save_indicator.py::SaveIndicator
def test_saving_immediately_after_enqueue_then_saved() -> None:
    src = _Src()
    ind = _ind(src)
    src.enqueued_seq = 5
    v = ind.view()
    assert (v.state, v.label, v.pending) == (SaveState.SAVING, "Saving...", 5)
    assert v.poll_ms <= SAVING_VISIBLE_WITHIN_MS == 250
    src.durable_seq = 5
    assert ind.view().state is SaveState.SAVED


# frob:tests python/sadi/api/save_indicator.py::SaveIndicator
def test_failure_latches_not_saved() -> None:
    src = _Src()
    ind = _ind(src)
    ind.mark_failed(IoError(reason="x", hint="Disk error"))
    src.durable_seq = src.enqueued_seq = 3
    v = ind.view()
    assert (v.state, v.label, v.hint) == (SaveState.NOT_SAVED, "NOT SAVED", "Disk error")


# frob:tests python/sadi/api/save_indicator.py::make_save_indicator_router
def test_route() -> None:
    src = _Src()
    src.enqueued_seq = 1
    app = FastAPI()
    app.include_router(make_save_indicator_router(_ind(src)))
    r = TestClient(app).get("/api/save-indicator")
    assert r.status_code == 200
    assert r.json()["state"] == "saving"
