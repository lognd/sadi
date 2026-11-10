"""REST routes for sessions, the wizard and points; handlers only delegate to SessionService."""

# frob:ticket 01M6W7R3XY1B0BF689RX3H80G2

from __future__ import annotations

import logging

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
    RunPhaseBody,
    RunPhaseView,
    SessionCreate,
    SessionInfo,
    SessionResume,
    SessionSummary,
    StepRef,
)
from sadi.server.service import SessionService

_log = logging.getLogger(__name__)

#: Manifest state of a session whose fold failed; never counts as newer work.
INCOMPLETE = "incomplete"
CLOSED = "closed"
JOINED = "joined"


# frob:ticket 01M72D2TZS82YV31D8FPXPD3AB
def _supersedes(kid: SessionSummary) -> bool:
    """True when `kid` counts as newer work than its parent.

    A spill import supersedes its parent only when it genuinely joined and closed cleanly; a
    fragment or crashed import never does (the parent holds the calibration and the points).
    """
    if kid.state == INCOMPLETE:
        return False
    if kid.spill_import is not None:
        return kid.spill_import == JOINED and kid.state == CLOSED
    return True


# frob:ticket 01M727965F98C8FB295P7A7FRS
def _descendants(items: list[SessionSummary], name: str) -> list[SessionSummary]:
    """Complete versions that descend from `name` through `parent` links (not `name` itself)."""
    kids: dict[str, list[SessionSummary]] = {}
    for item in items:
        if item.parent is not None:
            kids.setdefault(item.parent, []).append(item)
    out: list[SessionSummary] = []
    seen = {name}
    stack = [name]
    while stack:
        for kid in kids.get(stack.pop(), []):
            if kid.name in seen:
                continue
            seen.add(kid.name)
            if _supersedes(kid):  # frob:ticket 01M72T4R3X8833V8Z978SH4481
                out.append(kid)
                stack.append(kid.name)
            elif kid.spill_import is None:
                stack.append(kid.name)  # an incomplete child may still have complete descendants
            # a non-superseding spill import (fragment/crashed) holds only its own records, so
            # its subtree does not descend from the parent's data: never walk through it
    return out


# frob:ticket 01M727965F98C8FB295P7A7FRS
def mark_latest(items: list[SessionSummary]) -> list[SessionSummary]:
    """Flag a version `latest=False` only when a complete version descends from it by `parent`.

    Version numbers do not mean lineage: a branch resumed from an old version is a leaf of its
    own and stays latest; `incomplete` versions never supersede their parent, but a complete
    descendant (a recovered spill successor) does supersede an incomplete version.
    """
    out: list[SessionSummary] = []
    for item in items:
        newer = _descendants(items, item.name)
        if not newer:
            out.append(item)
            continue
        leaf = max(newer, key=lambda i: i.version)
        out.append(item.model_copy(update={"latest": False, "latest_name": leaf.name}))
    return out


# frob:ticket 01M727965F98C8FB295P7A7FRS
def newer_than(items: list[SessionSummary], name: str) -> list[str]:
    """Names of complete versions descended from `name` (empty if unknown or a leaf)."""
    me = next((i for i in items if i.name == name), None)
    if me is None:
        return []
    return [i.name for i in _descendants(items, name)]


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
        return mark_latest(svc.list_sessions())

    @r.post("/sessions", status_code=201)
    def create(body: SessionCreate) -> SessionInfo:
        """Create and open a new session."""
        return unwrap(svc.create(body))

    @r.post("/sessions/resume", status_code=201)
    def resume(body: SessionResume) -> SessionInfo:
        """Resume a session as a new version."""
        newer = newer_than(svc.list_sessions(), body.name)
        if newer:
            _log.warning("resuming %s although newer versions exist: %s", body.name, newer)
        info = unwrap(svc.resume(body.name))
        return info.model_copy(update={"newer_versions": newer})

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

    @r.get("/session/run-phase")
    def run_phase() -> RunPhaseView:
        """The recorded guided-run phase and the next allowed one."""
        return unwrap(svc.run_phase())

    @r.post("/session/run-phase")
    def enter_run_phase(body: RunPhaseBody) -> RunPhaseView:
        """Enter the next guided-run phase (409 when out of order); recorded durably."""
        return unwrap(svc.enter_phase(body.phase))

    return r
