"""Request and response models of the REST API (the OpenAPI contract for the web client)."""

# frob:ticket 01M6W7R3XY1B0BF689RX3H80G2

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sadi.core.wizard import History, WizardState
from sadi.labs.lctt.guidance import Phase
from sadi.store.events import CurrentPoint, EditOp, PointWindow
from sadi.synthetic.provenance import REAL, DataProvenance


class _Body(BaseModel):
    """Base for request bodies: unknown fields are rejected, never silently dropped."""

    model_config = ConfigDict(extra="forbid")


class LabInfo(BaseModel):
    """A registered lab the operator can start a session for."""

    id: str
    title: str


class SessionCreate(_Body):
    """Start a new session family for `lab`."""

    lab: str = Field(min_length=1)
    slug: str = "session"
    specimen: dict[str, str] = {}


class SessionResume(_Body):
    """Resume the session version directory named `name` as a new version."""

    name: str = Field(min_length=1)


class SessionSummary(BaseModel):
    """One session version on disk, as listed (manifest data only; never primary data)."""

    name: str
    family: str
    version: int
    lab: str
    state: str
    parent: str | None = None
    provenance: DataProvenance = REAL  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
    # frob:ticket 01M71XGK2GSEZ1GM3N3ES7916A
    latest: bool = True  # True for the newest version of its family
    latest_name: str | None = None  # directory of the newest version when this one is not it


class SessionInfo(BaseModel):
    """The open session: identity, lineage and its durable high-water mark."""

    name: str
    lab: str
    parent: str | None = None
    parent_last_seq: int | None = None
    durable_seq: int
    provenance: DataProvenance = REAL  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
    # frob:ticket 01M71XGK2GSEZ1GM3N3ES7916A
    newer_versions: list[str] = []  # newer versions of the resumed family that exist on disk


class StepRef(_Body):
    """Names the step an action applies to (must be the current one)."""

    step: str = Field(min_length=1)


class RevertBody(_Body):
    """Reopen the latest finished step; `step` (optional) must name exactly that step."""

    step: str | None = None


class CaptureBody(_Body):
    """Capture a point from typed `inputs` of `phase` over the raw sample `window`."""

    phase: str = Field(min_length=1)
    inputs: dict[str, Any]
    window: PointWindow
    t_since_load_s: float | None = None
    drift_rate: float | None = None
    settled: bool = False
    forced_early: bool = False
    # frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class EditBody(_Body):
    """Append an edit of point `target` (or `analysis`); history is kept, nothing is deleted."""

    op: EditOp
    args: dict[str, Any] = {}


class PointView(BaseModel):
    """A captured point with its edits applied."""

    point_id: str
    seq: int
    phase: str
    excluded: bool
    inputs: dict[str, Any]
    window: PointWindow
    history: tuple[str, ...]
    settled: bool = False
    forced_early: bool = False
    # frob:ticket 01M6WV1BEFANVC4BZ2S63NEPH5
    t_since_load_s: float | None = None
    drift_rate: float | None = None

    @staticmethod
    def of(cur: CurrentPoint) -> PointView:
        """Project a replayed `CurrentPoint` onto the wire shape."""
        return PointView(
            point_id=cur.point.point_id,
            seq=cur.seq,
            phase=cur.point.phase,
            excluded=cur.excluded,
            inputs=cur.inputs,
            window=cur.window,
            history=cur.history,
            settled=cur.point.settled,
            forced_early=cur.point.forced_early,
            t_since_load_s=cur.point.t_since_load_s,
            drift_rate=cur.point.drift_rate,
        )


class Committed(BaseModel):
    """What an accepted write produced: the durable seq, the new wizard state and history."""

    seq: int
    summary: str
    wizard: WizardState
    history: History


class RunPhaseBody(_Body):
    """Request to enter a guided-run phase (must be the next one in order)."""

    # frob:ticket 01M6XAKF5AK7FCJNBHPM62NYRS
    phase: Phase


class RunPhaseView(BaseModel):
    """The recorded guided-run phase (None for sessions that never recorded one) and the next."""

    # frob:ticket 01M6XAKF5AK7FCJNBHPM62NYRS
    phase: Phase | None
    next_phase: Phase | None
