"""Module-logger helper: one place that configures logging and hands out named loggers."""

from __future__ import annotations

import logging
import sys
import threading
from typing import TextIO, cast

_LOCK = threading.Lock()
_STATE = {"initialized": False}
_ROOT = "sadi"


class _LiveStreamHandler(logging.StreamHandler[TextIO]):
    """StreamHandler that looks up sys.stdout/sys.stderr at emit time, not at construction."""

    def __init__(self, stream_name: str) -> None:
        """Remember which `sys` attribute (`stdout` or `stderr`) to resolve per emit."""
        self._stream_name = stream_name
        super().__init__()

    @property
    def stream(self) -> TextIO:
        """Return the current `sys.<stream_name>` so capture/redirection is honored."""
        return cast(TextIO, sys.stderr if self._stream_name == "stderr" else sys.stdout)

    @stream.setter
    def stream(self, value: object) -> None:
        """Ignore assignment; the stream is always resolved live from `sys`."""


class _BelowWarning(logging.Filter):
    """Pass records strictly below WARNING so stdout stays free of errors."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Return True for DEBUG and INFO records only."""
        return record.levelno < logging.WARNING


class _Formatter(logging.Formatter):
    """Plain message for DEBUG/INFO; WARNING and above prefix the level name."""

    def format(self, record: logging.LogRecord) -> str:
        """Render the record as `LEVEL: msg` at WARNING+, else the bare message."""
        msg = record.getMessage()
        if record.levelno >= logging.WARNING:
            return f"{record.levelname}: {msg}"
        return msg


def _init() -> None:
    """Attach stdout/stderr handlers to the `sadi` logger once, thread-safely."""
    with _LOCK:
        if _STATE["initialized"]:
            return
        root = logging.getLogger(_ROOT)
        root.setLevel(logging.DEBUG)
        out = _LiveStreamHandler("stdout")
        out.setLevel(logging.DEBUG)
        out.addFilter(_BelowWarning())
        out.setFormatter(_Formatter())
        err = _LiveStreamHandler("stderr")
        err.setLevel(logging.WARNING)
        err.setFormatter(_Formatter())
        root.addHandler(out)
        root.addHandler(err)
        _STATE["initialized"] = True


def get_logger(name: str) -> logging.Logger:
    """Return the logger for `name` (use `__name__`), configuring logging on first call."""
    _init()
    return logging.getLogger(name)
