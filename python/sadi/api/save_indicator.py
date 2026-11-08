"""Save indicator: derive Saving / Saved / NOT SAVED from writer seqs, read-only (docs/ux.md s5)."""

# frob:ticket 01M6WJT06TWZW314324QF0DHB3
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Protocol

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from sadi.logging_setup import get_logger
from sadi.store.writer_thread import WriterError

_log = get_logger(__name__)

# Clients poll at most this often; the state flips to Saving on the first poll after a submit.
SAVING_VISIBLE_WITHIN_MS = 250


class SaveState(StrEnum):
    """The three header save states; NOT_SAVED only on a durable-write failure."""

    SAVED = "saved"
    SAVING = "saving"
    NOT_SAVED = "not_saved"


class SaveView(BaseModel):
    """What the header shows; `label` is the exact user-facing text."""

    model_config = ConfigDict(frozen=True)
    state: SaveState
    label: str
    pending: int
    saved_at: str | None = None
    hint: str = ""
    poll_ms: int = SAVING_VISIBLE_WITHIN_MS


class SeqSource(Protocol):
    """The slice of WriterHandle the indicator reads (never mutates)."""

    @property
    def durable_seq(self) -> int:
        """Highest durable seq."""
        ...

    @property
    def enqueued_seq(self) -> int:
        """Highest assigned seq."""
        ...


class SaveIndicator:
    """Tracks the save state: Saving the moment anything is enqueued but not yet durable."""

    def __init__(
        self,
        source: SeqSource,
        *,
        clock: Callable[[], float] = time.time,
        fmt_time: Callable[[float], str] | None = None,
    ) -> None:
        """Bind to a seq source; `clock` (epoch s) and `fmt_time` are injectable for tests."""
        self._source = source
        self._clock = clock
        self._fmt = fmt_time or (lambda t: time.strftime("%H:%M:%S", time.localtime(t)))
        self._lock = threading.Lock()
        self._failure: WriterError | None = None
        self._saved_at: float | None = None
        self._last: SaveState | None = None

    def mark_failed(self, error: WriterError) -> None:
        """Latch NOT SAVED (register as a WriterHandle.on_failure listener); never clears."""
        with self._lock:
            self._failure = error
        _log.error("save indicator latched NOT SAVED: %s", error)

    def view(self) -> SaveView:
        """Compute the current view; cheap and lock-light so it fits the 250 ms poll."""
        durable = self._source.durable_seq
        enqueued = self._source.enqueued_seq
        pending = max(0, enqueued - durable)
        with self._lock:
            if self._failure is not None:
                view = SaveView(
                    state=SaveState.NOT_SAVED,
                    label="NOT SAVED",
                    pending=pending,
                    hint=self._failure.hint,
                )
            elif pending > 0:
                view = SaveView(state=SaveState.SAVING, label="Saving...", pending=pending)
            else:
                if self._saved_at is None or self._last is not SaveState.SAVED:
                    self._saved_at = self._clock()
                stamp = self._fmt(self._saved_at)
                view = SaveView(
                    state=SaveState.SAVED,
                    label=f"Saved {stamp}",
                    pending=0,
                    saved_at=stamp,
                )
            if view.state is not self._last:
                _log.info("save indicator %s -> %s (pending=%d)", self._last, view.state, pending)
                self._last = view.state
            return view


def make_save_indicator_router(indicator: SaveIndicator) -> APIRouter:
    """Build GET /api/save-indicator; read-only, never touches the store."""
    router = APIRouter(prefix="/api/save-indicator", tags=["save"])

    @router.get("", response_model=SaveView)
    async def get_save_indicator() -> SaveView:
        """Return the current save state for the header."""
        return indicator.view()

    return router
