"""Test-side lock-order tracer and deadlock watchdog (concurrency.md sections 10 and 14.3)."""

# frob:ticket 01M6W7RAY4KTF866Q0Y7B4SZGG
from __future__ import annotations

import faulthandler
import logging
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

_log = logging.getLogger("sadi.tests.concurrency.tracing")


@dataclass
class LockTracer:
    """Records every acquire and the order violations it implies (thread-safe)."""

    violations: list[str] = field(default_factory=list)
    acquires: int = 0
    _held: threading.local = field(default_factory=threading.local)
    _guard: threading.Lock = field(default_factory=threading.Lock)

    def held(self) -> list[tuple[int, str]]:
        """Return the (level, name) stack held by the calling thread."""
        stack: list[tuple[int, str]] = []
        existing = getattr(self._held, "stack", None)
        if existing is None:
            self._held.stack = stack
            return stack
        return cast("list[tuple[int, str]]", existing)

    def on_acquire(self, level: int, name: str) -> None:
        """Record an acquire; flag it if the thread holds a lock of the same or deeper level."""
        stack = self.held()
        with self._guard:
            self.acquires += 1
            for hlevel, hname in stack:
                if hlevel >= level:
                    msg = f"order: acquired L{level} {name} while holding L{hlevel} {hname}"
                    self.violations.append(msg)
                    _log.error(msg)
        stack.append((level, name))

    def on_release(self, level: int, name: str) -> None:
        """Pop the matching entry from the calling thread's held stack."""
        stack = self.held()
        stack.remove((level, name))


class TracedLock:
    """A `threading.Lock` stand-in that reports to a `LockTracer` (a context manager)."""

    def __init__(self, level: int, name: str, tracer: LockTracer) -> None:
        """Wrap a fresh lock at lock-order `level`."""
        self._lock = threading.Lock()
        self.level = level
        self.name = name
        self._tracer = tracer

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """Acquire the lock, tracing the order before blocking."""
        self._tracer.on_acquire(self.level, self.name)
        ok = self._lock.acquire(blocking, timeout)
        if not ok:
            self._tracer.on_release(self.level, self.name)
        return ok

    def release(self) -> None:
        """Release the lock and pop it from the trace."""
        self._lock.release()
        self._tracer.on_release(self.level, self.name)

    def __enter__(self) -> bool:
        """Acquire (blocking)."""
        return self.acquire()

    def __exit__(self, *exc: object) -> None:
        """Release."""
        self.release()


class DeadlockError(AssertionError):
    """A scenario did not finish within its deadline (the deadlock detector fired)."""


def run_with_deadline(fn: Callable[[], None], timeout_s: float, name: str) -> None:
    """Run `fn` on a thread; on timeout dump all stacks and raise `DeadlockError`.

    The only wait is `Thread.join(timeout)`, a bounded wait on the scenario itself, never a
    sleep used as synchronisation.
    """
    errors: list[BaseException] = []

    def body() -> None:
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller thread
            errors.append(exc)

    t = threading.Thread(target=body, name=f"scenario-{name}", daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        _log.error("%s: no progress within %.1fs, dumping stacks", name, timeout_s)
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        raise DeadlockError(f"{name}: not finished within {timeout_s}s")
    if errors:
        raise errors[0]
