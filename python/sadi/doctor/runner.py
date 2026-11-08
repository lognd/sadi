"""Parallel, dependency-ordered, time-boxed scheduler for doctor checks (generic over results)."""

# frob:ticket 01M6WJHW2KET2M1730MZVJ1X4E
from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeVar

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = ["Abort", "Budget", "schedule"]

T = TypeVar("T")
Abort = Literal["check-timeout", "run-timeout", "crashed"]
DEFAULT_CHECK_TIMEOUT_S = 30.0
DEFAULT_RUN_TIMEOUT_S = 120.0
DEEP_RUN_TIMEOUT_S = 900.0
DEFAULT_WORKERS = 4


@dataclass(frozen=True)
class Budget:
    """Time and concurrency limits for one run: per check, whole run, worker threads."""

    check_timeout_s: float = DEFAULT_CHECK_TIMEOUT_S
    run_timeout_s: float = DEFAULT_RUN_TIMEOUT_S
    workers: int = DEFAULT_WORKERS

    @classmethod
    def for_deep(cls, deep: bool) -> Budget:
        """Return the default budget, with the longer whole-run limit for --deep."""
        return cls(run_timeout_s=DEEP_RUN_TIMEOUT_S if deep else DEFAULT_RUN_TIMEOUT_S)


def schedule(
    order: Sequence[str],
    deps: Mapping[str, tuple[str, ...]],
    work: Callable[[str], T],
    gate: Callable[[str, Mapping[str, T]], T | None],
    aborted: Callable[[str, Abort], T],
    budget: Budget,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, T]:
    """Run `work` for every id in `order`, parallel but only after its in-selection deps finish.

    `gate` (scheduler thread only) may short-circuit an id with a ready result; `aborted`
    builds the result for a check that timed out, a run that ran out of budget, or a crash.
    A timed-out worker thread is abandoned (daemon), so the run never hangs on it.
    """
    selected = set(order)
    waits = {i: tuple(d for d in deps.get(i, ()) if d in selected and d != i) for i in order}
    done: dict[str, T] = {}
    pending = list(order)
    running: dict[str, float] = {}
    inbox: queue.Queue[tuple[str, T | None, BaseException | None]] = queue.Queue()
    run_deadline = clock() + budget.run_timeout_s
    _log.info(
        "schedule: %d checks, %d workers, check budget %.1fs, run budget %.1fs",
        len(order),
        budget.workers,
        budget.check_timeout_s,
        budget.run_timeout_s,
    )

    def launch(ident: str) -> None:
        def target() -> None:
            try:
                inbox.put((ident, work(ident), None))
            except BaseException as exc:  # noqa: BLE001 - reported to the scheduler, not lost
                inbox.put((ident, None, exc))

        running[ident] = clock() + budget.check_timeout_s
        threading.Thread(target=target, name=f"doctor-{ident}", daemon=True).start()

    def advance() -> None:
        progressed = True
        while progressed:
            progressed = False
            for ident in list(pending):
                if any(d not in done for d in waits[ident]):
                    continue
                short = gate(ident, done)
                if short is not None:
                    pending.remove(ident)
                    done[ident] = short
                    progressed = True
                elif len(running) < budget.workers:
                    pending.remove(ident)
                    launch(ident)

    while True:
        advance()
        if not pending and not running:
            break
        if not running and pending:
            raise ValueError(f"dependency cycle among {sorted(pending)}")
        now = clock()
        if now >= run_deadline:
            _log.warning("run budget exhausted: %d running, %d pending", len(running), len(pending))
            for ident in [*running, *pending]:
                done[ident] = aborted(ident, "run-timeout")
            break
        nearest = min([*running.values(), run_deadline])
        try:
            ident, value, exc = inbox.get(timeout=max(nearest - now, 0.0))
        except queue.Empty:
            now = clock()
            for ident in [i for i, d in running.items() if d <= now]:
                _log.warning("check %s timed out after %.1fs", ident, budget.check_timeout_s)
                del running[ident]
                done[ident] = aborted(ident, "check-timeout")
            continue
        if ident not in running:  # late answer from an abandoned thread
            _log.debug("dropping late result of %s", ident)
            continue
        del running[ident]
        if exc is not None:
            _log.error("check %s crashed the worker: %r", ident, exc)
            done[ident] = aborted(ident, "crashed")
        else:
            assert value is not None
            done[ident] = value
    return done
