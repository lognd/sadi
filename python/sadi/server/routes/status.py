"""Status route: GET /api/status reports firmware, sample rate and the ACTIVE data root."""

# frob:ticket 01M71T683VDS38T2GYYW9SXT5B

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from fastapi import APIRouter
from pydantic import BaseModel

from sadi.logging_setup import get_logger

_log = get_logger(__name__)


class StatusSource(Protocol):
    """What the route needs from live acquisition: firmware text and the stream rate."""

    @property
    def firmware(self) -> str:
        """Device firmware string, "unknown" when not reported."""
        ...

    @property
    def sample_rate_hz(self) -> float:
        """Effective sample rate of streamed frames in Hz."""
        ...


class StatusOut(BaseModel):
    """Body of GET /api/status; null means the backend has no live device to ask."""

    firmware: str | None
    sample_rate_hz: float | None
    data_root: str


def make_status_router(data_root: Path, source: StatusSource | None) -> APIRouter:
    """Build the status router for the active `data_root` and an optional live `source`."""
    router = APIRouter()
    root = str(data_root.resolve())

    @router.get("/api/status", response_model=StatusOut)
    async def get_status() -> StatusOut:
        """Report firmware, sample rate and the active (not default) data root."""
        out = StatusOut(
            firmware=None if source is None else source.firmware,
            sample_rate_hz=None if source is None else source.sample_rate_hz,
            data_root=root,
        )
        _log.debug("status: %s", out)
        return out

    return router
