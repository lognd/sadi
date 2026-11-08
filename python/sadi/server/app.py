"""FastAPI app factory: mounts the doctor and plugin routers with injected settings."""

# frob:ticket 01M6WKQCC4HJ5C8HXP946BRKXW
# frob:ticket 01M6WK31FEG5BZNZNZHVQ3HMMX
# frob:ticket 01M6WMJZPYNHZR0KHY2C6W07WH

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from sadi.api.save_indicator import FailableSeqSource, SaveIndicator, make_save_indicator_router
from sadi.logging_setup import get_logger
from sadi.plugins.registry import PluginRegistry
from sadi.server.routes_doctor import make_doctor_router
from sadi.server.routes_plugins import make_plugins_router
from sadi.store.lock import DataRootLock, LockIo, acquire
from sadi.store.session import RootLockFailed

_log = get_logger(__name__)


class AppSettings(BaseModel):
    """Injection point for the app: the plugin registry and the data root."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    registry: PluginRegistry = Field(default_factory=PluginRegistry)
    data_root: Path = Path("data")
    recover_stale: bool = False
    require_root_lock: bool = True
    writer: FailableSeqSource | None = None


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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Hold the data-root lock for the app's lifetime; fail startup or degrade when refused."""
    cfg = cast(AppSettings, app.state.settings)
    lock, failure = _take_lock(cfg)
    app.state.root_lock = lock
    app.state.root_lock_failure = failure
    if failure is not None and cfg.require_root_lock:
        raise RootLockStartupError(failure)
    try:
        yield
    finally:
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
    app.include_router(make_doctor_router())
    app.include_router(make_plugins_router(cfg.registry))
    _log.info("app created (data_root=%s, %d plugins)", cfg.data_root, len(cfg.registry.records()))
    return app
