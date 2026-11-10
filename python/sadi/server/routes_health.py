"""Liveness route: GET /api/health (no session required, never 409)."""

# frob:ticket 01M6WZZEHBSPSCHA90KQG3RK1T

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from sadi.doctor import resolve_data_root
from sadi.doctor.probes import RealProbes
from sadi.doctor.schema import RunOptions
from sadi.logging_setup import get_logger
from sadi.synthetic.provenance import REAL, DataProvenance

_log = get_logger(__name__)


class HealthOut(BaseModel):
    """Health payload consumed by web/src/api/client.ts getHealth."""

    status: str = "ok"
    version: str
    simulated: bool | None = None
    data_root: str | None = None  # cheap host fact; avoids running the doctor (audit8 M1)
    provenance: DataProvenance = REAL  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC


def _package_version() -> str:
    """Return the installed sadi version, or "unknown" when not installed."""
    try:
        return version("sadi")
    except PackageNotFoundError:
        _log.warning("sadi distribution metadata not found; reporting version 'unknown'")
        return "unknown"


def make_health_router(
    simulated: Callable[[], bool] | None = None,
    provenance: DataProvenance = REAL,
    data_root: Path | None = None,
) -> APIRouter:
    """Build the health router; `simulated` reports the sim flag, `data_root` the data folder."""
    # frob:ticket 01M72YAG3BHTR584JK3TY2DE40
    root = resolve_data_root(RunOptions(data_root=str(data_root) if data_root else None), RealProbes())
    router = APIRouter(prefix="/api", tags=["health"])

    @router.get("/health", response_model=HealthOut)
    async def get_health() -> HealthOut:
        """Return status "ok", the package version and the sim flag when known."""
        sim = simulated() if simulated is not None else None
        _log.debug("health ok (simulated=%s)", sim)
        return HealthOut(version=_package_version(), simulated=sim, provenance=provenance, data_root=root)

    return router
