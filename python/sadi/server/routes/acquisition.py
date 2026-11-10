"""REST route for live-run operator commands: POST /api/session/load-change and POST /api/acquisition/resume."""

# frob:ticket 01M6X1GGD923K25M13JM84ZB2J

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.core.pipeline import PipelineError
from sadi.logging_setup import get_logger
from sadi.server.live import LiveError
from sadi.server.routes.problem import ApiProblem, conflict, from_model, unwrap

_log = get_logger(__name__)

#: Marks a load change on the live run; Ok carries the WAL seq of the recorded marker.
LoadChanger = Callable[[], Result[int, object]]


#: Resumes streaming after an idle pause (no marker); Ok when the run is streaming.
Resumer = Callable[[], Result[None, object]]


# frob:ticket 01M7279606J0ZW8ZY1RZG2ZHS9
class ResumeOut(BaseModel):
    """Result of resuming: streaming is running again and nothing was written to the WAL."""

    model_config = ConfigDict(frozen=True)

    streaming: bool


class LoadChangeOut(BaseModel):
    """Result of marking a load change: the WAL seq of the durable load-applied marker."""

    model_config = ConfigDict(frozen=True)

    marker_seq: int


def _problem(err: object) -> ApiProblem:
    """Map a live/pipeline/writer refusal to a problem (409 for state conflicts)."""
    if isinstance(err, LiveError):
        return conflict("no_live_session", err.description, err.description)
    if isinstance(err, PipelineError):
        return conflict("acquisition_halted", err.description, err.description)
    if isinstance(err, BaseModel):
        return from_model(err, "store")
    return ApiProblem(
        type="urn:sadi:error:acquisition:unknown",
        title="unknown",
        status=500,
        detail=repr(err)[:300],
        hint="See the server log for details.",
    )


def mark_load_change(changer: LoadChanger | None) -> Result[LoadChangeOut, ApiProblem]:
    """Run `changer` (None when no live acquisition is wired) and map the outcome."""
    if changer is None:
        _log.warning("load change refused: server has no live acquisition")
        return Err(_problem(LiveError.NoLiveSession))
    res = changer()
    if res.is_err:
        _log.error("load change refused: %s", res.danger_err)
        return Err(_problem(res.danger_err))
    _log.info("load change recorded, marker seq=%d", res.danger_ok)
    return Ok(LoadChangeOut(marker_seq=res.danger_ok))


# frob:ticket 01M7279606J0ZW8ZY1RZG2ZHS9
def resume_streaming(resumer: Resumer | None) -> Result[ResumeOut, ApiProblem]:
    """Run `resumer` (None when no live acquisition is wired) and map the outcome."""
    if resumer is None:
        _log.warning("resume refused: server has no live acquisition")
        return Err(_problem(LiveError.NoLiveSession))
    res = resumer()
    if res.is_err:
        _log.error("resume refused: %s", res.danger_err)
        return Err(_problem(res.danger_err))
    return Ok(ResumeOut(streaming=True))


def make_acquisition_router(
    changer: LoadChanger | None, resumer: Resumer | None = None
) -> APIRouter:
    """Build the router; hooks are the live run's `mark_load_change` and `resume` (None -> 409)."""
    r = APIRouter(prefix="/api")

    @r.post("/session/load-change", tags=["acquisition"])
    def load_change() -> LoadChangeOut:
        """Mark that a load was applied: durably record it and start a new settle point."""
        return unwrap(mark_load_change(changer))

    @r.post("/acquisition/resume", tags=["acquisition"])
    def resume() -> ResumeOut:
        """Restart streaming after an idle pause; writes no marker and applies no load."""
        return unwrap(resume_streaming(resumer))

    return r
