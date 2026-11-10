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
# frob:ticket 01M6WTCA3WJA26T204SWR6VW70

# frob:ticket 01M6XA16Y0GEC333HA645FY2YX
# frob:ticket 01M729645YNC58VB5NTJE6Q1RK

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from sadi.api.save_indicator import FailableSeqSource, SaveIndicator, make_save_indicator_router
from sadi.core.pipeline import Bus
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.guidance import Phase
from sadi.logging_setup import get_logger
from sadi.plugins.registry import PluginRegistry
from sadi.server.curve_source import SessionReplayCache, make_curve_source
from sadi.server.live import LiveAcquisition
from sadi.server.results_stream import ResultsStream
from sadi.server.routes.acquisition import make_acquisition_router
from sadi.server.routes.clamp import make_clamp_router
from sadi.server.routes.design import make_design_router
from sadi.server.routes.export import make_export_router
from sadi.server.routes.inventory import InventoryProvider, make_inventory_router
from sadi.server.routes.plots import make_plots_router
from sadi.server.routes.problem import install_problem_handlers
from sadi.server.routes.results import (
    BudgetSource,
    DeviceProbe,
    make_guidance_provider,
    make_results_router,
)
from sadi.server.routes.sessions import make_sessions_router
from sadi.server.routes_doctor import make_doctor_router
from sadi.server.routes_health import make_health_router
from sadi.server.routes_plugins import make_plugins_router
from sadi.server.routes_stress_strain import CurveSource, make_stress_strain_router
from sadi.server.security import OriginGuard
from sadi.server.service import SessionService
from sadi.server.ws import StreamHub, make_ws_router
from sadi.store.lock import DataRootLock, LockIo, acquire
from sadi.store.session import RootLockFailed
from sadi.store.spill import import_all_spills
from sadi.store.writer_thread import WriterHandle

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
    live: LiveAcquisition | None = None
    device: DeviceProbe | None = None
    budgets: BudgetSource | None = None
    inventory: InventoryProvider | None = None
    results: ResultsStream | None = None
    # Set only by the launcher after the flag + typed phrase; never read from the environment.
    synthetic: bool = False  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
    # Extra exact Origins trusted for writes/WS (e.g. a dev server); local same-port is implicit.
    extra_origins: frozenset[str] = frozenset()


class _SessionWriterSource:
    """Seq source following the open session's real writer; idle (nothing pending) when none."""

    def __init__(self) -> None:
        """Start with no writer bound."""
        self._writer: WriterHandle | None = None

    def bind(self, writer: WriterHandle | None) -> None:
        """Point at the current session's writer (None once it is closing or closed)."""
        self._writer = writer
        _log.info("save indicator %s a session writer", "bound to" if writer else "unbound from")

    @property
    def durable_seq(self) -> int:
        """Highest durable seq of the bound writer (0 when none)."""
        w = self._writer
        return w.durable_seq if w is not None else 0

    @property
    def enqueued_seq(self) -> int:
        """Highest assigned seq of the bound writer (0 when none)."""
        w = self._writer
        return w.enqueued_seq if w is not None else 0


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


def _recorded_phase(sessions: SessionService) -> Phase | None:
    """The run phase recorded in the open session (None when none or unreadable)."""
    got = sessions.run_phase()
    return got.danger_ok.phase if got.is_ok else None


def _acq_state(live: LiveAcquisition) -> tuple[str | None, str | None]:
    """(stop_reason, fault text) of `live` for the status API."""
    # frob:ticket 01M724E09H9X4DDW9ATK14JQ5C
    fault = live.fault
    return live.stop_reason, None if fault is None else f"{fault.origin}: {fault.detail}"[:300]


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Build a fresh FastAPI app (no global state) with all routers mounted."""
    cfg = settings if settings is not None else AppSettings()
    app = FastAPI(title="SADI", lifespan=_lifespan)
    app.add_middleware(OriginGuard, extra_origins=cfg.extra_origins)
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

    # frob:ticket 01M720QDHPFPD9CNEADS1CA9V6
    session_src = _SessionWriterSource()
    indicator = SaveIndicator(cfg.writer if cfg.writer is not None else session_src)
    if cfg.writer is not None:
        cfg.writer.on_failure(indicator.mark_failed)
    app.state.save_indicator = indicator

    app.include_router(make_save_indicator_router(indicator))
    app.state.sessions = SessionService(cfg.data_root, cfg.labs or LabRegistry(), cfg.synthetic)
    install_problem_handlers(app)
    live = cfg.live

    def _on_open(writer: WriterHandle, path: Path) -> None:
        """Bind the save indicator to the new writer, then run the live-acquisition hook."""
        if cfg.writer is None:
            session_src.bind(writer)
            writer.on_failure(indicator.mark_failed)
        if live is not None:
            live.on_session_open(writer, path)

    def _before_close() -> None:
        """Run the live-acquisition hook; the indicator keeps the writer until it is drained."""
        if live is not None:
            live.on_session_close()

    app.state.sessions.set_hooks(_on_open, _before_close)
    if live is not None:
        app.state.sessions.set_capture_gate(
            live.capture_block_hint
        )  # frob:ticket 01M724AKWJV8BRNRR3Q43553VR
        # frob:ticket 01M724E09H9X4DDW9ATK14JQ5C
        # frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
        live.set_phase_source(lambda: _recorded_phase(cast(SessionService, app.state.sessions)))
        app.state.sessions.set_acquisition(live.finish, lambda: _acq_state(live))
    app.include_router(make_sessions_router(app.state.sessions))
    # frob:ticket 01M6XA21KQE5WEXAN39683H4S9
    app.include_router(make_clamp_router(app.state.sessions))
    app.include_router(make_design_router(app.state.sessions))
    # frob:ticket 01M6X1GGD923K25M13JM84ZB2J
    app.include_router(
        make_acquisition_router(
            cfg.live.mark_load_change if cfg.live else None,
            cfg.live.resume if cfg.live else None,
        )
    )
    app.include_router(
        make_results_router(
            app.state.sessions,
            cfg.labs or LabRegistry(),
            cfg.device,
            cfg.budgets,
            cfg.live.reconnect_device if cfg.live else None,
        )
    )
    replays = SessionReplayCache()  # one incremental replayer per session, shared
    app.include_router(make_export_router(app.state.sessions, cfg.labs or LabRegistry(), replays))
    app.include_router(make_plots_router(app.state.sessions, replays))
    app.include_router(make_inventory_router(app.state.sessions, cfg.inventory))
    app.include_router(make_doctor_router(cfg.data_root))
    # frob:ticket 01M6WZZEHBSPSCHA90KQG3RK1T
    _dev = cfg.device
    app.include_router(
        make_health_router(
            (lambda: _dev.status == "simulated") if _dev is not None else None,
            app.state.sessions.provenance(),
        )
    )
    app.include_router(make_plugins_router(cfg.registry))
    if cfg.bus is not None:
        app.state.results_stream = cfg.results or ResultsStream()
        device = cfg.device
        app.state.stream_hub = StreamHub(
            cfg.bus,
            app.state.sessions,
            app.state.results_stream,
            simulated=(lambda: device.status == "simulated") if device is not None else None,
            guidance=make_guidance_provider(app.state.sessions, cfg.labs or LabRegistry()),
            provenance=app.state.sessions.provenance(),
        )
        app.include_router(make_ws_router(app.state.stream_hub))
    sessions = cast(SessionService, app.state.sessions)

    def _open_path() -> Path | None:
        """Open session dir from the service, or None when nothing is open."""
        return sessions.session_path().unwrap_or(None)

    source = cfg.curve_source or make_curve_source(
        _open_path, replays
    )  # frob:ticket 01M726PZNXA6BEXH97TQPK3176
    app.include_router(make_stress_strain_router(source, app.state.sessions.provenance))
    _log.info("app created (data_root=%s, %d plugins)", cfg.data_root, len(cfg.registry.records()))
    return app
