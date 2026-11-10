"""REST routes for exporting the open session, and read-only export of closed sessions, through the lab export formats."""

# frob:ticket 01M6WWMSA41S7Y91W4RE16P75D
# frob:ticket 01M6WTCA3WJA26T204SWR6VW70
# frob:ticket 01M6WVADCSP63DBMYH3RNCXWTM

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result, propagate

from sadi.core.errors import ComputeCode, ComputeError
from sadi.core.lab import ExportFormat, LabId, LabModule
from sadi.core.models import RunState
from sadi.core.registry import LabRegistry
from sadi.logging_setup import get_logger
from sadi.server.curve_source import SessionReplayCache
from sadi.server.routes.problem import ApiProblem, ProblemError, from_sadi, not_found, unwrap
from sadi.server.schemas import PointView
from sadi.server.service import ClosedSession, SessionService
from sadi.server.session_points import active_points, analyze, to_captured
from sadi.store.exports import ExportError, write_export
from sadi.synthetic.provenance import EXPORT_PREFIX, PROVENANCE_HEADER, stamp_export

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


@propagate
def _open_lab(svc: SessionService, labs: LabRegistry) -> Result[tuple[str, LabModule], ApiProblem]:
    """Resolve the open session's name and lab, or the problem explaining why not."""
    info = svc.info().unwrap()
    lab = labs.get(LabId(info.lab)).unwrap(
        err=not_found(info.lab, "Register the session's lab or resume with another.")
    )
    return Ok((info.name, lab))


@propagate
def _render(
    lab: LabModule,
    name: str,
    sdir: Path,
    views: list[PointView],
    format_id: str,
    cache: SessionReplayCache | None,
) -> Result[tuple[ExportFormat, str, bytes], ApiProblem]:
    """Render `format_id` over `views` of the session at `sdir` in memory (shared by both paths)."""
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
    active = active_points(views)
    captured = to_captured(active)
    analysis = analyze(lab, active)
    if analysis.is_err:
        _log.warning("export %s: recompute failed: %s", format_id, analysis.danger_err)
        return Err(from_sadi(analysis.danger_err))
    # frob:ticket 01M6WVADB5YKXAVC43CQNBQVJW
    replays = cache if cache is not None else SessionReplayCache()
    events = replays.events(sdir, verify=True)  # frob:ticket 01M6X9CP3SGVZ93H22ARANVN2E
    if events.is_err:
        _log.error("export %s: session replay failed: %s", format_id, events.danger_err)
        return Err(from_sadi(ComputeError(code=ComputeCode.DEGENERATE, detail="session replay")))
    run = RunState(session_id=name, points=captured, events=tuple(events.danger_ok))
    body = fmt.writer(run, analysis.danger_ok)
    if body.is_err:
        _log.error("export %s: writer failed: %s", format_id, body.danger_err)
        return Err(from_sadi(body.danger_err))
    _log.info("exported %s for %s (%d bytes)", format_id, name, len(body.danger_ok))
    return Ok((fmt, name, body.danger_ok))


@propagate
def render_export(
    svc: SessionService,
    labs: LabRegistry,
    format_id: str,
    cache: SessionReplayCache | None = None,
) -> Result[tuple[ExportFormat, str, bytes], ApiProblem]:
    """Render `format_id` for the open session in memory; read-only, never stops acquisition."""
    name, lab = _open_lab(svc, labs).unwrap()
    views = svc.points().unwrap()
    return _render(lab, name, svc.session_path().unwrap(), views, format_id, cache)


# frob:ticket 01M724AKTJNNRY06637VBQ0A3E
@propagate
def render_closed_export(
    svc: SessionService,
    name: str,
    format_id: str,
    cache: SessionReplayCache | None = None,
) -> Result[tuple[ExportFormat, ClosedSession, bytes], ApiProblem]:
    """Render `format_id` for closed session `name` read-only: no writer, lock, version or device."""
    closed = svc.read_closed(name).unwrap()
    fmt, _, body = _render(closed.lab, name, closed.path, closed.views, format_id, cache).unwrap()
    return Ok((fmt, closed, body))


#: Response header naming the copy kept in the session folder ("failed" when it could not be kept).
SAVED_HEADER = "X-SADI-Saved"
#: Response header set to "segment/offset" when a closed export holds only the verified WAL prefix.
# frob:ticket 01M727965F98C8FB295P7A7FRS
TORN_TAIL_HEADER = "X-SADI-Torn-Tail"
#: Filename prefix on exports of a session whose torn tail was dropped (only the verified prefix was read).
RECOVERED_PREFIX = "RECOVERED-"


def stamp_recovered(body: bytes, media_type: str, torn_tail: str) -> bytes:
    """Brand a torn-tail export: a `# RECOVERED:` first line for CSV, a `recovered` key for JSON."""
    # frob:ticket 01M729FVNSJCVAHK4XBSG9NBYC
    note = (
        f"only the verified prefix of the session log was read (torn tail at {torn_tail}); "
        "the last few seconds may be missing"
    )
    if media_type == "application/json":
        try:
            doc = json.loads(body)
        except ValueError:
            doc = None
        if isinstance(doc, dict):
            doc["recovered"] = note
            return json.dumps(doc).encode("utf-8")
        return json.dumps({"recovered": note, "data": doc}).encode("utf-8")
    return f"# RECOVERED: {note}\n".encode() + body


#: Largest figure upload accepted (bytes); a 600 dpi plot is a few MB.
MAX_FIGURE_BYTES = 64 * 1024 * 1024
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _save_copy(  # frob:ticket 01M71XGK2GSEZ1GM3N3ES7916A
    svc: SessionService, kind: str, basename: str, ext: str, body: bytes
) -> str:
    """Keep an atomic, never-overwritten copy in the session's exports/ folder; return its path or ''."""
    path = svc.session_path()
    info = svc.info()
    if path.is_err or info.is_err:
        _log.error("export copy skipped: no open session")
        return ""
    # `ExportError` details are logged by write_export; the download itself must not fail.
    written = write_export(
        _Dir(path.danger_ok),
        kind,
        basename,
        ext,
        body,
        covers_seq=info.danger_ok.durable_seq or None,
        lab_module=info.danger_ok.lab,
    )
    if written.is_err:
        err: ExportError = written.danger_err
        _log.error("export copy of %s/%s not kept: %s", kind, basename, err)
        return ""
    rel = written.danger_ok.path.relative_to(path.danger_ok).as_posix()
    _log.info("export copy kept at %s", rel)
    return rel


class _Dir:
    """Minimal `_HasPath` for write_export: just a session directory."""

    def __init__(self, path: Path) -> None:
        """Remember the session directory."""
        self.path = path


def make_export_router(
    svc: SessionService, labs: LabRegistry, cache: SessionReplayCache | None = None
) -> APIRouter:
    """Build the export router over `svc`; handlers only delegate and never mutate the session."""
    replays = cache if cache is not None else SessionReplayCache()
    r = APIRouter(prefix="/api")

    @r.get("/export")
    def list_formats() -> list[ExportFormatView]:
        """List the open session's lab export formats."""
        _, lab = unwrap(_open_lab(svc, labs))
        return [_view(f) for f in lab.export_formats]

    @r.get("/export/{format_id}")
    def export(format_id: str) -> Response:
        """Stream one export: a CSV-style attachment, or inline JSON for figure data."""
        fmt, name, body = unwrap(render_export(svc, labs, format_id, replays))
        headers: dict[str, str] = {}
        prov = svc.provenance()
        if prov.synthetic:
            body = stamp_export(body, fmt.media_type, prov)
            headers[PROVENANCE_HEADER] = "synthetic"
        else:
            headers[PROVENANCE_HEADER] = "real"
        if _is_download(fmt):
            ext = _EXT.get(fmt.media_type, "bin")
            fname = f"{name}-{fmt.id}.{ext}"
            if prov.synthetic:
                fname = EXPORT_PREFIX + fname
            headers["Content-Disposition"] = f'attachment; filename="{fname}"'
            saved = _save_copy(svc, fmt.id, f"{name}-{fmt.id}", ext, body)
            headers[SAVED_HEADER] = saved or "failed"
        return Response(content=body, media_type=fmt.media_type, headers=headers)

    # frob:ticket 01M724AKTJNNRY06637VBQ0A3E
    @r.get("/sessions/{name}/export/{format_id}")
    def export_closed(name: str, format_id: str) -> Response:
        """Download one export of a closed session; read-only, so no copy is kept and nothing is written."""
        fmt, closed, body = unwrap(render_closed_export(svc, name, format_id, replays))
        headers = {PROVENANCE_HEADER: "real"}
        if closed.provenance.synthetic:
            body = stamp_export(body, fmt.media_type, closed.provenance)
            headers[PROVENANCE_HEADER] = "synthetic"
        if closed.torn_tail is not None:
            headers[TORN_TAIL_HEADER] = closed.torn_tail
            body = stamp_recovered(body, fmt.media_type, closed.torn_tail)
        if _is_download(fmt):
            fname = f"{name}-{fmt.id}.{_EXT.get(fmt.media_type, 'bin')}"
            if closed.provenance.synthetic:
                fname = EXPORT_PREFIX + fname
            if closed.torn_tail is not None:
                fname = RECOVERED_PREFIX + fname
            headers["Content-Disposition"] = f'attachment; filename="{fname}"'
        return Response(content=body, media_type=fmt.media_type, headers=headers)

    @r.post("/export/figure/{figure_id}")
    async def save_figure(figure_id: str, request: Request) -> dict[str, str]:
        """Keep a browser-rendered PNG/SVG figure in the session's exports/ folder (never overwrites)."""
        # frob:ticket 01M71XGK2GSEZ1GM3N3ES7916A
        name, _ = unwrap(_open_lab(svc, labs))  # 409 when no session is open
        data = await request.body()
        if not data or len(data) > MAX_FIGURE_BYTES:
            raise ProblemError(
                ApiProblem(
                    type="urn:sadi:error:input:bad_figure",
                    title="bad figure",
                    status=400,
                    detail=f"figure {figure_id}: empty or larger than {MAX_FIGURE_BYTES} bytes",
                    hint="Export the figure again at a lower DPI, or as SVG.",
                )
            )
        ext = "png" if data.startswith(_PNG_MAGIC) else "svg"
        saved = _save_copy(svc, "figure", f"{name}-{figure_id}", ext, data)
        return {"saved": saved or "failed"}

    return r
