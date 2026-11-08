"""Volume probes: the only doctor code that writes (DATA-040, opt-in) or locks (DATA-050)."""

# frob:ticket 01M6WJHVW6SP6XXPWX8QXARDHK
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

PROBE_DIR = "doctor"
FLUSHES = 5

FlushStatus = Literal["ok", "unsupported", "error"]
LockState = Literal["ok", "unsupported", "held", "error"]


@dataclass(frozen=True)
class FlushFacts:
    """What flushing one probe file observed."""

    status: FlushStatus = "ok"
    fullfsync: bool | None = None
    p50_ms: float = 0.0
    detail: str = ""


def _fullfsync(fd: int) -> bool | None:
    """Try F_FULLFSYNC (macOS); None when the platform has no such flag."""
    import fcntl

    flag = getattr(fcntl, "F_FULLFSYNC", None)
    if flag is None:
        return None
    try:
        fcntl.fcntl(fd, flag)
    except OSError:
        return False
    return True


def probe_flush(data_root: str) -> FlushFacts:
    """Create, fsync five times and delete one file under <root>/doctor/ (never sessions/)."""
    directory = Path(data_root) / PROBE_DIR
    path = directory / f"flush-{os.getpid()}.probe"
    fd = -1
    try:
        directory.mkdir(exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        times: list[float] = []
        for _ in range(FLUSHES):
            os.write(fd, b"sadi-doctor-flush\n")
            started = time.perf_counter()
            os.fsync(fd)
            times.append((time.perf_counter() - started) * 1000)
        full = _fullfsync(fd) if sys.platform == "darwin" else None
    except OSError as exc:
        _log.warning("flush probe failed under %s: %s", directory, exc)
        unsupported = exc.errno in (22, 95)  # EINVAL, EOPNOTSUPP
        return FlushFacts(status="unsupported" if unsupported else "error", detail=str(exc))
    finally:
        if fd >= 0:
            os.close(fd)
        path.unlink(missing_ok=True)
    times.sort()
    p50 = times[len(times) // 2]
    _log.debug("flush probe: p50 %.1f ms, fullfsync %s", p50, full)
    return FlushFacts(fullfsync=full, p50_ms=round(p50, 2))


def probe_lock(target: str) -> LockState:
    """Try a non-blocking lock on a read-only descriptor of target, then release it."""
    try:
        fd = os.open(target, os.O_RDONLY)
    except OSError as exc:
        _log.warning("lock probe cannot open %s: %s", target, exc)
        return "error"
    try:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            except OSError as exc:
                return "held" if exc.errno in (13, 36) else "unsupported"
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            return "ok"
        import errno
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return "held"
            return "unsupported" if exc.errno in (errno.ENOLCK, errno.EOPNOTSUPP) else "error"
        fcntl.flock(fd, fcntl.LOCK_UN)
        return "ok"
    finally:
        os.close(fd)
