"""Spawn-context worker surveys: the facts the WRK checks judge.

`selftest` and `watchdog` are the spawn targets; they live here (not in
`sadi.jobs`) so the doctor owns its probes and the child imports only `sadi`.
"""

# frob:ticket 01M6WJHVRVS94M67F41C3P2BMG
from __future__ import annotations

import multiprocessing
import sys
import time
from multiprocessing.connection import Connection
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

SPAWN_TIMEOUT_S = 30.0
WATCHDOG_EXIT_S = 5.0
SpawnStatus = Literal["ok", "fail", "timeout"]


class WorkerFacts(BaseModel):
    """What spawning a worker and orphaning it observed."""

    model_config = ConfigDict(frozen=True)
    spawn_status: SpawnStatus = "ok"
    spawn_seconds: float = 0.0
    imports_store: bool = False
    detail: str = ""
    orphan_survives: bool = False


class _Echo(BaseModel):
    """The model the selftest round-trips through the child."""

    n: int


def selftest(conn: Connection) -> None:
    """Child entry: echo a pydantic model and report whether sadi.store was imported."""
    echo = _Echo.model_validate(conn.recv())
    leaked = any(m == "sadi.store" or m.startswith("sadi.store.") for m in sys.modules)
    conn.send({"n": echo.n, "imports_store": leaked})
    conn.close()


def watchdog(ready: Connection, parent_end: Connection) -> None:
    """Child entry: announce readiness, then exit when the parent's pipe end closes."""
    ready.send("ready")
    try:
        while True:
            parent_end.recv()
    except EOFError:
        return


def _spawn_selftest() -> WorkerFacts:
    """Run `selftest` in a spawned child and judge its answer."""
    ctx = multiprocessing.get_context("spawn")
    mine, theirs = ctx.Pipe()
    t0 = time.monotonic()
    proc = ctx.Process(target=selftest, args=(theirs,), daemon=True)
    try:
        proc.start()
        theirs.close()
        mine.send({"n": 42})
        if not mine.poll(SPAWN_TIMEOUT_S):
            proc.kill()
            return WorkerFacts(spawn_status="timeout", detail=f"no answer in {SPAWN_TIMEOUT_S}s")
        reply = mine.recv()
        proc.join(SPAWN_TIMEOUT_S)
    except (OSError, EOFError) as exc:
        _log.warning("worker spawn failed: %s", exc)
        proc.kill()
        return WorkerFacts(
            spawn_status="fail", detail=str(exc), spawn_seconds=time.monotonic() - t0
        )
    finally:
        mine.close()
    dt = time.monotonic() - t0
    if reply.get("n") != 42 or proc.exitcode != 0:
        return WorkerFacts(
            spawn_status="fail", spawn_seconds=dt, detail=f"echo={reply!r} exit={proc.exitcode}"
        )
    return WorkerFacts(spawn_seconds=dt, imports_store=bool(reply.get("imports_store")))


def _orphan_survives() -> bool:
    """Spawn a watchdog child, close the parent end, and report whether it outlives 5 s."""
    ctx = multiprocessing.get_context("spawn")
    ready_r, ready_w = ctx.Pipe(duplex=False)
    pipe_r, pipe_w = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=watchdog, args=(ready_w, pipe_r), daemon=True)
    try:
        proc.start()
        ready_w.close()
        pipe_r.close()
        if not ready_r.poll(SPAWN_TIMEOUT_S):
            proc.kill()
            return True
        ready_r.recv()
        pipe_w.close()
        proc.join(WATCHDOG_EXIT_S)
        survives = proc.is_alive()
        if survives:
            proc.kill()
        return survives
    finally:
        ready_r.close()


def probe_workers() -> WorkerFacts:
    """Spawn the selftest worker, then the watchdog worker; never raises."""
    try:
        facts = _spawn_selftest()
        if facts.spawn_status != "ok":
            return facts
        return facts.model_copy(update={"orphan_survives": _orphan_survives()})
    except Exception as exc:  # noqa: BLE001 - any surprise is reported as a spawn failure
        _log.exception("worker probe crashed")
        return WorkerFacts(spawn_status="fail", detail=str(exc))
