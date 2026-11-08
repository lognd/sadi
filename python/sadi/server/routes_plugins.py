"""Read-only plugin status routes: GET /api/plugins and GET /api/plugins/{id}."""

# frob:ticket 01M6WFZF9FD9QNXP62MCETRNEA

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from typani import Err, Ok

from sadi.logging_setup import get_logger
from sadi.plugins.api import PluginStatus, get_plugin_status, list_plugin_status
from sadi.plugins.registry import PluginRegistry

_log = get_logger(__name__)


def make_plugins_router(registry: PluginRegistry) -> APIRouter:
    """Build the plugin status router over `registry`; the app factory mounts it (follow-up)."""
    router = APIRouter(prefix="/api/plugins", tags=["plugins"])

    @router.get("", response_model=list[PluginStatus])
    def list_plugins() -> list[PluginStatus]:
        """List every plugin, failed ones included, always with HTTP 200."""
        return list_plugin_status(registry)

    @router.get("/{plugin_id}", response_model=PluginStatus)
    def get_plugin(plugin_id: str) -> PluginStatus:
        """Return one plugin's status or 404 when the id is unknown."""
        res = get_plugin_status(registry, plugin_id)
        if isinstance(res, Ok):
            return res.value
        assert isinstance(res, Err)
        _log.info("GET plugin %r -> 404", plugin_id)
        raise HTTPException(status_code=404, detail=res.error.description)

    return router
