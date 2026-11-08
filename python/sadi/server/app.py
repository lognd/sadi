"""FastAPI app factory: mounts the doctor and plugin routers with injected settings."""

# frob:ticket 01M6WKQCC4HJ5C8HXP946BRKXW
# frob:ticket 01M6WK31FEG5BZNZNZHVQ3HMMX
# frob:ticket 01M6WMJZPYNHZR0KHY2C6W07WH
# frob:ticket 01M6WMSZKN488HTWG19V69GETD
# frob:ticket 01M6WMXEM0M76VKMN2WF3C3VYD
# frob:ticket 01M6WP4WV9B3SCJ0GY2M32XWZV
# frob:ticket 01M6W7R3XY1B0BF689RX3H80G2
# frob:ticket 01M6W7R3ZPY606D3MHG4QRM2GS
# frob:ticket 01M6WTCA1SET2XBYG05J73KJ11
# frob:ticket 01M6WTSF7KQ3YMJP9C0Z75HVRK

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from sadi.api.save_indicator import FailableSeqSource, SaveIndicator, make_save_indicator_router
from sadi.logging_setup import get_logger
from sadi.core.pipeline import Bus
from sadi.core.registry import LabRegistry
from sadi.plugins.registry import PluginRegistry
from sadi.server.curve_source import make_curve_source
from sadi.server.routes.inventory import InventoryProvider, make_inventory_router
from sadi.server.routes.problem import install_problem_handlers
from sadi.server.routes.results import BudgetSource, DeviceProbe, make_results_router
from sadi.server.routes.sessions import make_sessions_router
from sadi.server.routes_doctor import make_doctor_router
from sadi.server.routes_plugins import make_plugins_router
from sadi.server.routes_stress_strain import CurveSource, make_stress_strain_router
from sadi.server.service import SessionService
from sadi.server.ws import StreamHub, make_ws_router
from sadi.store.lock import DataRootLock, LockIo, acquire
from sadi.store.session import RootLockFailed
from sadi.store.spill import import_all_spills

_log = get_logger(__name__)


class AppSettings(BaseModel):
    """Injection point for the app: the plugin registry and the data root."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    registry: PluginRegistry = Field(default_factory=PluginRegistry)
    data_root: Path = Path("data")
    recover_stale: bool = False
    require_root_lock: bool = True
    writer: FailableSeqSource | None = None
    curve_source: CurveSource | None = None
    labs: LabRegistry | None = None
    bus: Bus | None = None
    device: DeviceProbe | None = None
    budgets: BudgetSource | None = None
    inventory: InventoryProvider | None = None


class _NoWriter:
    """Seq source used when no writer is injected: nothing pending, so the header reads Saved."""

    durable_seq = 0
    enqueued_seq = 0


class RootLockStartupError(RuntimeError):
    """Raised at app startup (launcher exits non-zero) when the data-root lock is refused."""

    def __init__(self, failure: RootLockFailed) -> None:
        """Wrap the typed `failure`; the message carries the user-facing hint."""
        super().__init__(f"cannot lock data root: {failure.hint}")
        self.failure = failure


def _take_lock(cfg: AppSettings) -> tuple[DataRootLock | None, RootLockFailed | None]:
    """Acquire the data-root lock without ever stealing a live one; return (lock, failure)."""
    try:
        cfg.data_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _log.error("cannot create data root %s: %s", cfg.data_root, exc)
        err = LockIo(path=cfg.data_root, errno=exc.errno, hint=str(exc))
        return None, RootLockFailed(error=err, hint=err.hint)
    got = acquire(cfg.data_root, recover_stale=cfg.recover_stale)
    if got.is_err:
        err = got.danger_err
        _log.error("data-root lock refused: %s", type(err).__name__)
        return None, RootLockFailed(error=err, hint=err.hint)
    return got.danger_ok, None


def _import_spills(cfg: AppSettings) -> int:
    """Import emergency spills (lock held); log each, never delete; return the failure count."""
    failures = 0
    for spill, outcome in import_all_spills(cfg.data_root):
        if outcome.is_err:
            failures += 1
            _log.error("spill %s NOT imported (file kept intact): %s", spill, outcome.danger_err)
        elif outcome.danger_ok is None:
            _log.info("spill %s already imported", spill)
        else:
            rep = outcome.danger_ok
            _log.warning(
                "recovered spill %s as %s (%d records)", spill, rep.version_dir, rep.record_count
            )
    return failures


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Hold the data-root lock for the app's lifetime; fail startup or degrade when refused."""
    cfg = cast(AppSettings, app.state.settings)
    lock, failure = _take_lock(cfg)
    app.state.root_lock = lock
    app.state.root_lock_failure = failure
    if failure is not None and cfg.require_root_lock:
        raise RootLockStartupError(failure)
    app.state.spill_failures = _import_spills(cfg) if lock is not None else 0
    try:
        yield
    finally:
        cast(SessionService, app.state.sessions).shutdown()
        if lock is not None:
            lock.release()
            _log.info("data-root lock released on shutdown")


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Build a fresh FastAPI app (no global state) with all routers mounted."""
    cfg = settings if settings is not None else AppSettings()
    app = FastAPI(title="SADI", lifespan=_lifespan)
    app.state.settings = cfg
    app.state.root_lock = None
    app.state.root_lock_failure = None
    app.state.spill_failures = 0

    @app.get("/api/root-lock")
    async def root_lock_state() -> dict[str, object]:
        """Report whether this process holds the data-root lock (ok=false when degraded)."""
        failure = cast(RootLockFailed | None, app.state.root_lock_failure)
        if failure is None:
            return {"ok": app.state.root_lock is not None}
        return {"ok": False, "kind": type(failure.error).__name__, "hint": failure.hint}

    indicator = SaveIndicator(cfg.writer if cfg.writer is not None else _NoWriter())
    if cfg.writer is not None:
        cfg.writer.on_failure(indicator.mark_failed)
    app.state.save_indicator = indicator

    app.include_router(make_save_indicator_router(indicator))
    app.state.sessions = SessionService(cfg.data_root, cfg.labs or LabRegistry())
    install_problem_handlers(app)
    app.include_router(make_sessions_router(app.state.sessions))
    app.include_router(
        make_results_router(app.state.sessions, cfg.labs or LabRegistry(), cfg.device, cfg.budgets)
    )
    app.include_router(make_inventory_router(app.state.sessions, cfg.inventory))
    app.include_router(make_doctor_router())
    app.include_router(make_plugins_router(cfg.registry))
    if cfg.bus is not None:
        app.state.stream_hub = StreamHub(cfg.bus, app.state.sessions)
        app.include_router(make_ws_router(app.state.stream_hub))
    source = cfg.curve_source or make_curve_source(cfg.data_root)
    app.include_router(make_stress_strain_router(source))
    _log.info("app created (data_root=%s, %d plugins)", cfg.data_root, len(cfg.registry.records()))
    return app
