"""FastAPI app factory: mounts the doctor and plugin routers with injected settings."""

# frob:ticket 01M6WKQCC4HJ5C8HXP946BRKXW

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from sadi.logging_setup import get_logger
from sadi.plugins.registry import PluginRegistry
from sadi.server.routes_doctor import make_doctor_router
from sadi.server.routes_plugins import make_plugins_router

_log = get_logger(__name__)


class AppSettings(BaseModel):
    """Injection point for the app: the plugin registry and the data root."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    registry: PluginRegistry = Field(default_factory=PluginRegistry)
    data_root: Path = Path("data")


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Build a fresh FastAPI app (no global state) with the doctor and plugin routers mounted."""
    cfg = settings if settings is not None else AppSettings()
    app = FastAPI(title="SADI")
    app.state.settings = cfg
    app.include_router(make_doctor_router())
    app.include_router(make_plugins_router(cfg.registry))
    _log.info("app created (data_root=%s, %d plugins)", cfg.data_root, len(cfg.registry.records()))
    return app
