"""Liveness route: GET /api/health (no session required, never 409)."""

# frob:ticket 01M6WZZEHBSPSCHA90KQG3RK1T

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter
from pydantic import BaseModel

from sadi.logging_setup import get_logger

_log = get_logger(__name__)


class HealthOut(BaseModel):
    """Health payload consumed by web/src/api/client.ts getHealth."""

    status: str = "ok"
    version: str
    simulated: bool | None = None


def _package_version() -> str:
    """Return the installed sadi version, or "unknown" when not installed."""
    try:
        return version("sadi")
    except PackageNotFoundError:
        _log.warning("sadi distribution metadata not found; reporting version 'unknown'")
        return "unknown"


def make_health_router(simulated: Callable[[], bool] | None = None) -> APIRouter:
    """Build the health router; `simulated` optionally reports the sim-device flag."""
    router = APIRouter(prefix="/api", tags=["health"])

    @router.get("/health", response_model=HealthOut)
    async def get_health() -> HealthOut:
        """Return status "ok", the package version and the sim flag when known."""
        sim = simulated() if simulated is not None else None
        _log.debug("health ok (simulated=%s)", sim)
        return HealthOut(version=_package_version(), simulated=sim)

    return router
