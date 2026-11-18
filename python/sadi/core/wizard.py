"""Wizard framework: step state machine, undo/redo command log and step-rail projection.

Everything is a pure function of the lab's `StepSpec`s and the session's `ReplayState`; the
wizard owns no state and does no I/O. Each action returns `Result[Command, WizardError]`: a
`Command` is the WAL records the caller must append (then replay to see the new state). Nothing
is ever rewritten or deleted (data-safety.md): undo and redo are compensating EDIT records, and
undoing a captured point appends an `exclude` edit so the point itself stays in the log.
"""

# frob:ticket 01M6W7R335N9GPFD4DYXP2D6HY

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result, propagate

from sadi.core.lab import CaptureKind, StepId, StepSpec, needs_device
from sadi.core.models import Phase
from sadi.core.point_inputs import PHASE_SPECIMEN, check_ranges, parse_inputs
from sadi.logging_setup import get_logger
from sadi.store.events import (
    ANALYSIS_TARGET,
    CurrentPoint,
    EditOp,
    EditV1,
    PointV1,
    PointWindow,
    ReplayState,
    edit_record,
    marker_record,
    point_record,
)
from sadi.store.records import MarkerV1, NewRecord

_log = get_logger(__name__)

#: Marker kinds the wizard writes; the label is the step id.
MARK_DONE = "wizard.step_done"
MARK_SKIPPED = "wizard.step_skipped"
MARK_REVERTED = "wizard.step_reverted"
#: Note on the `exclude` edit that compensates (undoes) a point capture.
UNDO_CAPTURE_NOTE = "wizard:undo_capture"

_POINT_OPS: frozenset[str] = frozenset({"exclude", "include", "set_window", "override_input"})


class WizardError(ErrorSet):
    """Why a wizard action was refused; the description is the hint shown in the UI."""

    NoSteps = "The lab declares no steps; nothing to run"
    DuplicateStep = "Two steps share an id; fix the lab's step list"
    UnknownStep = "That step does not exist in this lab"
    Gated = "An earlier step is not finished; complete it or skip it explicitly first"
    NeedPoints = "This step needs more captured points before it can be completed (or skip it)"
    NotCurrent = "Only the current step can be completed or skipped"
    NothingToRevert = "No finished step to reopen"
    NotLatest = "Only the most recently finished step can be reopened"
    NoCapture = "The current step does not capture device points"
    PhaseMismatch = "The point was captured in a different phase than the current step"
    UnknownPoint = "That point does not exist; pick a captured point"
    BadEdit = "That edit is not valid here; use exclude, include, set_window or override_input"
    BadWindow = "The averaging window is invalid; first/last sample or seq are inconsistent"
    BadInput = "That input value is not valid: use a finite, in-range number for a known field"
    NothingToUndo = "Nothing to undo"
    NothingToRedo = "Nothing to redo (a new action clears the redo history)"


class StepStatus(StrEnum):
    """Where a step stands on the rail."""

    DONE = "done"
    SKIPPED = "skipped"
    CURRENT = "current"
    LOCKED = "locked"


class _Frozen(BaseModel):
    """Base for immutable wizard values."""

    model_config = ConfigDict(frozen=True)


class RailItem(_Frozen):
    """One entry of the step rail: what the UI draws and whether it can be acted on."""

    id: StepId
    title: str
    phase: Phase
    capture: CaptureKind
    status: StepStatus
    needs_device: bool
    hint: str = ""


class WizardState(_Frozen):
    """Derived wizard position: the rail, the current step and any odd marker events."""

    rail: tuple[RailItem, ...]
    current: StepId | None
    anomalies: tuple[str, ...] = ()

    @property
    def finished(self) -> bool:
        """Return True when every step is done or skipped."""
        return self.current is None


class Command(_Frozen):
    """The WAL records an accepted action needs appended, with a one-line summary for the log."""

    records: tuple[NewRecord, ...]
    summary: str


class Action(_Frozen):
    """One undoable user action: a captured point or a substantive edit."""

    kind: str
    ref: str
    label: str


class History(_Frozen):
    """Undo and redo stacks, oldest first; the last element is what undo/redo would act on."""

    undo: tuple[Action, ...] = ()
    redo: tuple[Action, ...] = ()

    @property
    def can_undo(self) -> bool:
        """Return True when undo would do something."""
        return bool(self.undo)

    @property
    def can_redo(self) -> bool:
        """Return True when redo would do something."""
        return bool(self.redo)


def _mark(kind: str, step: StepId) -> NewRecord:
    """Build the MARKER record for a step transition."""
    return marker_record(MarkerV1(kind=kind, label=str(step)))


def _resolved(
    steps: list[StepSpec],
    state: ReplayState,
    anomalies: list[str],
    seqs: dict[StepId, int] | None = None,
) -> dict[StepId, str]:
    """Fold wizard markers into step -> MARK_DONE/MARK_SKIPPED, enforcing sequential order.

    When `seqs` is given it receives the seq of each applied resolving marker.
    """
    known = [s.id for s in steps]
    out: dict[StepId, str] = {}
    for entry in state.markers:
        m = entry.marker
        if not m.kind.startswith("wizard."):
            continue
        sid = StepId(m.label)
        if sid not in known:
            anomalies.append(f"seq {entry.seq}: marker for unknown step {m.label}")
        elif m.kind in (MARK_DONE, MARK_SKIPPED):
            if known[len(out)] != sid:
                anomalies.append(f"seq {entry.seq}: {sid} resolved out of order; ignored")
            else:
                out[sid] = m.kind
                if seqs is not None:
                    seqs[sid] = entry.seq
        elif m.kind == MARK_REVERTED:
            if out and list(out)[-1] == sid:
                del out[sid]
                if seqs is not None:
                    seqs.pop(sid, None)
            else:
                anomalies.append(f"seq {entry.seq}: revert of {sid} which is not the latest")
        else:
            anomalies.append(f"seq {entry.seq}: unknown wizard marker {m.kind}")
    return out


class Wizard:
    """Stateless wizard over one lab's steps; every method takes the session's ReplayState."""

    def __init__(self, steps: list[StepSpec]) -> None:
        """Keep the lab's ordered steps (use `Wizard.create` to validate them)."""
        self.steps = list(steps)

    @staticmethod
    def create(steps: list[StepSpec]) -> Result[Wizard, WizardError]:
        """Build a Wizard, refusing an empty list or duplicate step ids."""
        if not steps:
            _log.error("wizard: lab declares no steps")
            return Err(WizardError.NoSteps)
        ids = [s.id for s in steps]
        if len(set(ids)) != len(ids):
            _log.error("wizard: duplicate step ids in %s", ids)
            return Err(WizardError.DuplicateStep)
        _log.info("wizard: created with %d steps", len(steps))
        return Ok(Wizard(steps))

    # ---- step state machine ---------------------------------------------------------------

    def state(self, replay: ReplayState) -> WizardState:
        """Derive the rail and current step from the steps and recorded markers."""
        anomalies: list[str] = []
        resolved = _resolved(self.steps, replay, anomalies)
        items: list[RailItem] = []
        current: StepId | None = None
        for spec in self.steps:
            if spec.id in resolved:
                status = StepStatus.DONE if resolved[spec.id] == MARK_DONE else StepStatus.SKIPPED
                hint = ""
            elif current is None:
                current, status, hint = spec.id, StepStatus.CURRENT, ""
            else:
                prev = self._title(current)
                status, hint = StepStatus.LOCKED, f"Finish or skip '{prev}' first"
            items.append(
                RailItem(
                    id=spec.id,
                    title=spec.title,
                    phase=spec.phase,
                    capture=spec.capture,
                    status=status,
                    needs_device=needs_device(spec.capture),
                    hint=hint,
                )
            )
        return WizardState(rail=tuple(items), current=current, anomalies=tuple(anomalies))

    def _title(self, sid: StepId) -> str:
        """Return the title of step `sid`."""
        return next(s.title for s in self.steps if s.id == sid)

    def _spec(self, sid: StepId) -> StepSpec | None:
        """Return the step `sid` or None."""
        return next((s for s in self.steps if s.id == sid), None)

    def _gate(self, replay: ReplayState, sid: StepId) -> Result[None, WizardError]:
        """Accept only the current step; explain why otherwise."""
        if self._spec(sid) is None:
            _log.warning("wizard: unknown step %s", sid)
            return Err(WizardError.UnknownStep)
        st = self.state(replay)
        if st.current == sid:
            return Ok(None)
        item = next(i for i in st.rail if i.id == sid)
        _log.info("wizard: step %s refused (%s)", sid, item.status)
        return Err(
            WizardError.Gated if item.status is StepStatus.LOCKED else WizardError.NotCurrent
        )

    @propagate
    def complete(self, replay: ReplayState, sid: StepId) -> Result[Command, WizardError]:
        """Mark the current step done once its `min_points` criterion holds."""
        self._gate(replay, sid).unwrap()
        spec = self._spec(sid)
        assert spec is not None  # _gate accepted it
        have = self._step_points(replay, spec)
        if have < spec.min_points:
            _log.info("wizard: complete %s refused, %d/%d points", sid, have, spec.min_points)
            return Err(WizardError.NeedPoints)
        _log.info("wizard: complete %s", sid)
        return Ok(Command(records=(_mark(MARK_DONE, sid),), summary=f"completed {sid}"))

    def not_ready(self, replay: ReplayState, sid: StepId) -> str | None:
        """Return why step `sid` fails its lab quality gate (`complete_check`), else None."""
        spec = self._spec(sid)
        if spec is None or spec.complete_check is None:
            return None
        why = spec.complete_check(self._step_inputs(replay, spec))
        if why is not None:
            _log.info("wizard: complete %s blocked by quality gate: %s", sid, why)
        return why

    def _step_inputs(self, replay: ReplayState, spec: StepSpec) -> list[dict[str, Any]]:
        """Inputs of the step's active points captured since the previous step resolved."""
        return [dict(p.inputs) for p in self._step_point_views(replay, spec)]

    def _step_point_views(self, replay: ReplayState, spec: StepSpec) -> list[CurrentPoint]:
        """Active points of the step's phase captured since the previous step resolved."""
        seqs: dict[StepId, int] = {}
        _resolved(self.steps, replay, [], seqs)
        ids = [s.id for s in self.steps]
        idx = ids.index(spec.id)
        since = seqs.get(ids[idx - 1], 0) if idx else 0
        return [
            p
            for p in replay.view().points
            if not p.excluded and p.point.phase == spec.phase.value and p.seq > since
        ]

    def _step_points(self, replay: ReplayState, spec: StepSpec) -> int:
        """Count active points of the step's phase captured since the previous step resolved."""
        return len(self._step_point_views(replay, spec))

    @propagate
    def skip(self, replay: ReplayState, sid: StepId) -> Result[Command, WizardError]:
        """Explicitly skip the current step (the only way past a step without completing it)."""
        self._gate(replay, sid).unwrap()
        _log.info("wizard: skip %s", sid)
        return Ok(Command(records=(_mark(MARK_SKIPPED, sid),), summary=f"skipped {sid}"))

    def revert(
        self, replay: ReplayState, sid: StepId | None = None
    ) -> Result[Command, WizardError]:
        """Reopen the most recently finished step (a compensating marker; history is kept)."""
        st = self.state(replay)
        done = [i.id for i in st.rail if i.status in (StepStatus.DONE, StepStatus.SKIPPED)]
        if not done:
            return Err(WizardError.NothingToRevert)
        if sid is not None and self._spec(sid) is None:
            return Err(WizardError.UnknownStep)
        if sid is not None and sid != done[-1]:
            _log.info("wizard: revert %s refused, latest is %s", sid, done[-1])
            return Err(WizardError.NotLatest)
        target = done[-1]
        _log.info("wizard: revert %s", target)
        return Ok(Command(records=(_mark(MARK_REVERTED, target),), summary=f"reopened {target}"))

    # ---- actions that write data ----------------------------------------------------------

    def capture(self, replay: ReplayState, point: PointV1) -> Result[Command, WizardError]:
        """Record a captured point; only valid on a device-capturing current step."""
        st = self.state(replay)
        spec = self._spec(st.current) if st.current is not None else None
        if spec is None or not needs_device(spec.capture):
            _log.info("wizard: capture refused, current step %s", st.current)
            return Err(WizardError.NoCapture)
        # frob:ticket 01M6X6PW1F4HNNFMMY5YV3QKP9
        if point.phase == PHASE_SPECIMEN:
            _log.info("wizard: specimen point %s accepted during %s", point.point_id, spec.id)
        elif point.phase != spec.phase.value:
            _log.warning("wizard: capture phase %s != step phase %s", point.phase, spec.phase)
            return Err(WizardError.PhaseMismatch)
        _log.info("wizard: capture point %s in %s", point.point_id, spec.id)
        return Ok(Command(records=(point_record(point),), summary=f"captured {point.point_id}"))

    def edit(
        self, replay: ReplayState, target: str, op: EditOp, args: dict[str, object] | None = None
    ) -> Result[Command, WizardError]:
        """Record an edit of a point, or a fit-window edit with target `analysis`."""
        args = dict(args or {})
        if target == ANALYSIS_TARGET:
            if op != "set_fit_window":
                return Err(WizardError.BadEdit)
        else:
            if op not in _POINT_OPS:
                return Err(WizardError.BadEdit)
            view = replay.view()
            current = next((p for p in view.points if p.point.point_id == target), None)
            if current is None:
                _log.warning("wizard: edit of unknown point %s", target)
                return Err(WizardError.UnknownPoint)
            if op == "set_window" and not _window_ok(current.window, args):
                return Err(WizardError.BadWindow)
            # frob:ticket 01M72D3CTDED2MGDY721RSM8M4
            phase, inputs = current.point.phase, current.inputs
            if op == "override_input" and not _override_ok(phase, inputs, args):
                return Err(WizardError.BadInput)
        edit = EditV1(target=target, op=op, args=args)
        _log.info("wizard: edit %s %s %s", edit.edit_id, op, target)
        return Ok(Command(records=(edit_record(edit),), summary=f"{op} {target}"))

    # ---- undo / redo ----------------------------------------------------------------------

    def history(self, replay: ReplayState) -> History:
        """Project the undo and redo stacks from the log (pure fold, deterministic)."""
        undo, redo = _fold_history(replay)
        return History(undo=tuple(u[0] for u in undo), redo=tuple(r[0] for r in redo))

    def undo(self, replay: ReplayState) -> Result[Command, WizardError]:
        """Compensate the latest active action; a capture is excluded, an edit is superseded."""
        undo, _ = _fold_history(replay)
        if not undo:
            return Err(WizardError.NothingToUndo)
        action, target = undo[-1]
        if action.kind == "point":
            edit = EditV1(target=action.ref, op="exclude", note=UNDO_CAPTURE_NOTE)
        else:
            edit = EditV1(target=target, op="undo", supersedes=action.ref)
        _log.info("wizard: undo %s %s via edit %s", action.kind, action.ref, edit.edit_id)
        return Ok(Command(records=(edit_record(edit),), summary=f"undo {action.label}"))

    def redo(self, replay: ReplayState) -> Result[Command, WizardError]:
        """Re-apply the latest undone action by superseding the compensating edit."""
        _, redo = _fold_history(replay)
        if not redo:
            return Err(WizardError.NothingToRedo)
        action, target, token = redo[-1]
        op: EditOp = "undo" if action.kind == "point" else "redo"
        edit = EditV1(target=target, op=op, supersedes=token)
        _log.info("wizard: redo %s %s via edit %s", action.kind, action.ref, edit.edit_id)
        return Ok(Command(records=(edit_record(edit),), summary=f"redo {action.label}"))


def _override_ok(phase: str, current: dict[str, object], args: dict[str, object]) -> bool:
    """Return True when `args` merged over `current` parses and passes the capture range checks.

    Unknown keys, `phase`, strings, booleans and NaN/Infinity are refused (nothing is stored).
    """
    # frob:ticket 01M72D3CTDED2MGDY721RSM8M4
    match parse_inputs(phase, dict(current)):
        case Err(why):
            _log.warning("wizard: override_input refused, current inputs unreadable: %s", why)
            return False
        case Ok(base):
            allowed = set(type(base).model_fields) - {"phase"}
    for key, val in args.items():
        if key not in allowed or not _finite_number(val):
            _log.warning("wizard: override_input refused for %s=%r", key, val)
            return False
    match parse_inputs(phase, {**current, **args}).and_then(check_ranges):
        case Err(why):
            _log.warning("wizard: override_input refused: %s", why)
            return False
        case Ok(_):
            return True


def _finite_number(val: object) -> bool:
    """Return True for a real, finite int/float (booleans, strings, NaN and Infinity are not)."""
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val)


def _window_ok(window: PointWindow, args: dict[str, object]) -> bool:
    """Return True when `args` merged over `window` is a valid, ordered window."""
    try:
        merged = PointWindow.model_validate({**window.model_dump(), **args})
    except ValueError:
        return False
    return merged.first_raw_seq <= merged.last_raw_seq and (
        merged.first_raw_seq != merged.last_raw_seq or merged.first_sample <= merged.last_sample
    )


_UndoEntry = tuple[Action, str]
_RedoEntry = tuple[Action, str, str]


def _fold_history(replay: ReplayState) -> tuple[list[_UndoEntry], list[_RedoEntry]]:
    """Fold points and edits in seq order into undo entries (action, target) and redo entries.

    A redo entry is (action, target, token) where token is the edit_id of the compensating edit
    that a redo must supersede. A new action clears the redo stack.
    """
    events: list[tuple[int, PointV1 | EditV1]] = [(p.seq, p.point) for p in replay.points]
    events += [(e.seq, e.edit) for e in replay.edits]
    events.sort(key=lambda ev: ev[0])
    undo: list[_UndoEntry] = []
    redo: list[_RedoEntry] = []
    capture_comp: dict[str, tuple[Action, str]] = {}
    seen: set[str] = set()
    for _, ev in events:
        if isinstance(ev, PointV1):
            if ev.point_id in seen:
                continue
            seen.add(ev.point_id)
            undo.append(
                (Action(kind="point", ref=ev.point_id, label=f"capture {ev.point_id}"), ev.point_id)
            )
            redo.clear()
        elif ev.op == "exclude" and ev.note == UNDO_CAPTURE_NOTE:
            hit = next((u for u in undo if u[0].kind == "point" and u[0].ref == ev.target), None)
            if hit is None:
                _log.warning("history: capture undo of non-active point %s", ev.target)
                continue
            undo.remove(hit)
            redo.append((hit[0], ev.target, ev.edit_id))
            capture_comp[ev.edit_id] = hit
        elif ev.op == "undo" and ev.supersedes in capture_comp:
            hit_r = next((r for r in redo if r[2] == ev.supersedes), None)
            if hit_r is not None:
                redo.remove(hit_r)
                undo.append((hit_r[0], hit_r[1]))
        elif ev.op == "undo":
            hit = next((u for u in undo if u[0].kind == "edit" and u[0].ref == ev.supersedes), None)
            if hit is None:
                _log.warning("history: undo of non-active edit %s", ev.supersedes)
                continue
            undo.remove(hit)
            redo.append((hit[0], hit[1], ev.edit_id))
        elif ev.op == "redo":
            hit_r = next((r for r in redo if r[2] == ev.supersedes), None)
            if hit_r is not None:
                redo.remove(hit_r)
                undo.append((hit_r[0], hit_r[1]))
        else:
            label = f"{ev.op} {ev.target}"
            undo.append((Action(kind="edit", ref=ev.edit_id, label=label), ev.target))
            redo.clear()
    return undo, redo
