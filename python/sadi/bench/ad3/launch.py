"""Launcher-side AD3 lifecycle: open on request, ALWAYS close before exit (else Adept segfaults)."""

# frob:ticket 01M6Z52N7A69ET20H5GMS8S7BG
from __future__ import annotations

import atexit
import contextlib
import logging
import os
import signal
import threading
from collections.abc import Callable, Generator, Mapping
from types import FrameType, TracebackType

from typani import Err, Ok, Result

from sadi.bench.ad3.backend import DwfError
from sadi.bench.ad3.device import Ad3Closed, Ad3Session
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = ["AD3_ENV", "Ad3Guard", "ad3_requested", "open_managed_ad3"]

AD3_ENV = "SADI_AD3"
_TRUTHY = ("1", "true", "yes")
_EXIT_SIGNALS = (signal.SIGTERM, signal.SIGHUP) if hasattr(signal, "SIGHUP") else (signal.SIGTERM,)

_Handler = Callable[[int, FrameType | None], object] | int | None
Loader = Callable[[], Result[Ad3Closed, DwfError]]


def ad3_requested(flag: bool, env: Mapping[str, str] | None = None) -> bool:
    """Return whether an AD3 is wanted: the `--ad3` flag or `SADI_AD3` set to 1/true/yes."""
    values = os.environ if env is None else env
    return flag or values.get(AD3_ENV, "").strip().lower() in _TRUTHY


def _safe_log(level: int, msg: str, *args: object) -> None:
    """Log without ever raising: a signal can land mid-write and make a handler re-enter."""
    try:
        _log.log(level, msg, *args)
    except Exception:  # noqa: BLE001 - logging must never abort or mask a device close
        pass


@contextlib.contextmanager
def _logging_muted() -> Generator[None]:
    """Mute logging during a signal-driven close; a log call there can re-enter a stream."""
    prev = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(prev)


class Ad3Guard:
    """Owns an open Ad3Session and guarantees one close: context exit, atexit or exit signal."""

    def __init__(self, session: Ad3Session) -> None:
        """Take ownership of `session` and arm the atexit close."""
        self.session = session
        self._lock = threading.RLock()  # re-entrant: a signal may land inside close()
        self._closing = False
        self._done = False
        self._prev: dict[int, _Handler] = {}
        atexit.register(self.close)

    @property
    def closed(self) -> bool:
        """True once the device close has been attempted."""
        return self._done

    def close(self) -> Result[None, DwfError]:
        """Close the device exactly once; later calls are Ok no-ops. Never raises."""
        with self._lock:
            if self._done:
                return Ok(None)
            self._done = True
            self._closing = True
        atexit.unregister(self.close)
        # Stay armed until the device is closed: a second signal must not kill mid-close.
        try:
            res = self.session.close()
        finally:
            self._closing = False
        self._restore_signals()
        if isinstance(res, Err):
            _safe_log(logging.ERROR, "ad3 guard close failed: %s", res.unwrap_err().code.value)
            return Err(res.unwrap_err())
        _safe_log(logging.INFO, "ad3 guard closed device")
        return Ok(None)

    def install_signal_handlers(self) -> None:
        """Map SIGTERM/SIGHUP to SystemExit so the device is closed (main thread only)."""
        if threading.current_thread() is not threading.main_thread():
            _log.warning("ad3 signal handlers skipped: not on the main thread")
            return
        for sig in _EXIT_SIGNALS:
            if sig in self._prev:
                continue  # idempotent: never save our own handler as the "prior" one
            self._prev[sig] = signal.signal(sig, self._on_signal)

    def _on_signal(self, signum: int, _frame: FrameType | None) -> None:
        """Close the device FIRST, log after (never raising), then SystemExit(128+signum)."""
        if self._closing:
            _safe_log(logging.WARNING, "signal %d during ad3 close; letting it finish", signum)
            return
        failed = True
        try:
            with _logging_muted():  # backend/session log calls could re-enter stdout too
                failed = self.close().is_err
        finally:
            # Logging only after the close: a reentrant stream write must not skip it.
            _safe_log(logging.WARNING, "signal %d received; ad3 closed before exit", signum)
            if failed:
                _safe_log(logging.ERROR, "ad3 close during signal %d failed", signum)
        raise SystemExit(128 + signum)

    def _restore_signals(self) -> None:
        """Put back the handlers saved by install_signal_handlers."""
        if threading.current_thread() is threading.main_thread():
            for sig, prev in self._prev.items():
                # None means the prior handler was not installed from Python; fall back to default.
                signal.signal(sig, signal.SIG_DFL if prev is None else prev)
        self._prev.clear()

    def __enter__(self) -> Ad3Guard:
        """Enter the context with the device open."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close on leaving, including on exceptions; a failed close is logged, not raised."""
        if self.close().is_err:
            _log.error("ad3 close on context exit failed")


def open_managed_ad3(loader: Loader | None = None, index: int = -1) -> Result[Ad3Guard, str]:
    """Load libdwf and open the AD3 under a guard; Err(str) with fix hints, never a crash."""
    load = loader or Ad3Closed.from_library
    closed = load()
    if isinstance(closed, Err):
        err = closed.unwrap_err()
        _log.error("ad3 unavailable: %s", err.code.value)
        return Err(f"ad3 unavailable ({err.code.value}): {err.detail}\n{err.hint}")
    dev = closed.unwrap()
    dev.index = index
    opened = dev.open()
    if isinstance(opened, Err):
        err = opened.unwrap_err()
        _log.error("ad3 open failed: %s", err.code.value)
        return Err(f"ad3 open failed ({err.code.value}): {err.detail}\n{err.hint}")
    guard = Ad3Guard(opened.unwrap())
    guard.install_signal_handlers()
    return Ok(guard)
