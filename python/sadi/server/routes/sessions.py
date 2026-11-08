"""REST routes for sessions, the wizard and points; handlers only delegate to SessionService."""

# frob:ticket 01M6W7R3XY1B0BF689RX3H80G2

from __future__ import annotations

from fastapi import APIRouter

from sadi.core.wizard import History, WizardState
from sadi.server.routes.problem import unwrap
from sadi.server.schemas import (
    CaptureBody,
    Committed,
    EditBody,
    LabInfo,
    PointView,
    RevertBody,
    SessionCreate,
    SessionInfo,
    SessionResume,
    SessionSummary,
    StepRef,
)
from sadi.server.service import SessionService


def make_sessions_router(svc: SessionService) -> APIRouter:
    """Build the /api router over `svc`; sync handlers run in the threadpool, off the loop."""
    r = APIRouter(prefix="/api")

    @r.get("/labs")
    def labs() -> list[LabInfo]:
        """List registered labs."""
        return svc.labs()

    @r.get("/sessions")
    def sessions() -> list[SessionSummary]:
        """List session versions on disk."""
        return svc.list_sessions()

    @r.post("/sessions", status_code=201)
    def create(body: SessionCreate) -> SessionInfo:
        """Create and open a new session."""
        return unwrap(svc.create(body))

    @r.post("/sessions/resume", status_code=201)
    def resume(body: SessionResume) -> SessionInfo:
        """Resume a session as a new version."""
        return unwrap(svc.resume(body.name))

    @r.get("/session")
    def info() -> SessionInfo:
        """Describe the open session."""
        return unwrap(svc.info())

    @r.post("/session/close", status_code=204)
    def close() -> None:
        """Close the open session."""
        unwrap(svc.close())

    @r.get("/session/wizard")
    def wizard() -> WizardState:
        """Wizard rail and current step."""
        return unwrap(svc.wizard_state())

    @r.post("/session/wizard/complete")
    def complete(body: StepRef) -> Committed:
        """Complete the current step."""
        return unwrap(svc.complete(body.step))

    @r.post("/session/wizard/skip")
    def skip(body: StepRef) -> Committed:
        """Skip the current step."""
        return unwrap(svc.skip(body.step))

    @r.post("/session/wizard/revert")
    def revert(body: RevertBody) -> Committed:
        """Reopen a finished step."""
        return unwrap(svc.revert(body.step))

    @r.get("/session/points")
    def points() -> list[PointView]:
        """List captured points."""
        return unwrap(svc.points())

    @r.post("/session/points", status_code=201)
    def capture(body: CaptureBody) -> Committed:
        """Capture a point."""
        return unwrap(svc.capture(body))

    @r.post("/session/points/{target}/edit")
    def edit(target: str, body: EditBody) -> Committed:
        """Edit a point; the original stays in the log."""
        return unwrap(svc.edit(target, body))

    @r.post("/session/undo")
    def undo() -> Committed:
        """Undo the latest action."""
        return unwrap(svc.undo())

    @r.post("/session/redo")
    def redo() -> Committed:
        """Redo the latest undone action."""
        return unwrap(svc.redo())

    @r.get("/session/history")
    def history() -> History:
        """Undo and redo stacks."""
        return unwrap(svc.history())

    return r
