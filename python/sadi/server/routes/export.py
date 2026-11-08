"""REST routes for exporting the open session through its lab's export formats (read-only)."""

# frob:ticket 01M6WTCA3WJA26T204SWR6VW70

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.core.lab import ExportFormat, LabId, LabModule
from sadi.core.models import RunState
from sadi.core.registry import LabRegistry
from sadi.logging_setup import get_logger
from sadi.server.routes.problem import ApiProblem, from_sadi, not_found, unwrap
from sadi.server.routes.results import _captured, _points_for
from sadi.server.service import SessionService

_log = get_logger(__name__)

#: File extension per media type; anything else downloads as `.bin`.
_EXT = {"text/csv": "csv", "application/json": "json"}


class ExportFormatView(BaseModel):
    """One export format as listed on the wire."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    media_type: str
    download: bool


def _is_download(fmt: ExportFormat) -> bool:
    """Figure data (JSON) is consumed inline by the web plots; everything else downloads."""
    return fmt.media_type != "application/json"


def _view(fmt: ExportFormat) -> ExportFormatView:
    """Project an `ExportFormat` onto its wire view."""
    return ExportFormatView(
        id=fmt.id, title=fmt.title, media_type=fmt.media_type, download=_is_download(fmt)
    )


def _open_lab(svc: SessionService, labs: LabRegistry) -> Result[tuple[str, LabModule], ApiProblem]:
    """Resolve the open session's name and lab, or the problem explaining why not."""
    info = svc.info()
    if info.is_err:
        return Err(info.danger_err)
    got = labs.get(LabId(info.danger_ok.lab))
    if got.is_err:
        return Err(
            not_found(info.danger_ok.lab, "Register the session's lab or resume with another.")
        )
    return Ok((info.danger_ok.name, got.danger_ok))


def render_export(
    svc: SessionService, labs: LabRegistry, format_id: str
) -> Result[tuple[ExportFormat, str, bytes], ApiProblem]:
    """Render `format_id` for the open session in memory; nothing is written to disk or the WAL."""
    opened = _open_lab(svc, labs)
    if opened.is_err:
        return Err(opened.danger_err)
    name, lab = opened.danger_ok
    fmt = next((f for f in lab.export_formats if f.id == format_id), None)
    if fmt is None:
        _log.warning("unknown export format %r for lab %s", format_id, lab.id)
        known = ", ".join(f.id for f in lab.export_formats) or "none"
        return Err(
            not_found(
                format_id,
                f"Pick one of this lab's formats ({known}); GET /api/export lists them.",
            )
        )
    pts = svc.points()
    if pts.is_err:
        return Err(pts.danger_err)
    captured = _captured(_points_for(pts.danger_ok))
    analysis = lab.recompute(captured)
    if analysis.is_err:
        _log.warning("export %s: recompute failed: %s", format_id, analysis.danger_err)
        return Err(from_sadi(analysis.danger_err))
    run = RunState(session_id=name, points=captured)
    body = fmt.writer(run, analysis.danger_ok)
    if body.is_err:
        _log.error("export %s: writer failed: %s", format_id, body.danger_err)
        return Err(from_sadi(body.danger_err))
    _log.info("exported %s for %s (%d bytes)", format_id, name, len(body.danger_ok))
    return Ok((fmt, name, body.danger_ok))


def make_export_router(svc: SessionService, labs: LabRegistry) -> APIRouter:
    """Build the export router over `svc`; handlers only delegate and never mutate the session."""
    r = APIRouter(prefix="/api")

    @r.get("/export")
    def list_formats() -> list[ExportFormatView]:
        """List the open session's lab export formats."""
        _, lab = unwrap(_open_lab(svc, labs))
        return [_view(f) for f in lab.export_formats]

    @r.get("/export/{format_id}")
    def export(format_id: str) -> Response:
        """Stream one export: a CSV-style attachment, or inline JSON for figure data."""
        fmt, name, body = unwrap(render_export(svc, labs, format_id))
        headers: dict[str, str] = {}
        if _is_download(fmt):
            ext = _EXT.get(fmt.media_type, "bin")
            headers["Content-Disposition"] = f'attachment; filename="{name}-{fmt.id}.{ext}"'
        return Response(content=body, media_type=fmt.media_type, headers=headers)

    return r
