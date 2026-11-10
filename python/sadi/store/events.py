"""Point/edit/settings/marker event log and deterministic replay (data-safety.md sections 2.3, 3.3).

Nothing is edited in place: points, window edits, exclusions, settings and markers are WAL
records and "current state" is a pure fold over them. `ReplayState` keeps the full history
(every point, edit, settings change and marker); `ReplayState.view()` derives the current values.
Replay never raises on odd content: unreadable or unknown records are listed in `skipped`, and
semantically odd ones (edit of an unknown point) in `View.anomalies`; the WAL is never touched.
"""

# frob:ticket 01M6W7R2F3KJWQCWEKZK6BT3MG
from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.store import snapshot
from sadi.store.records import (
    FLAG_JSON,
    MarkerV1,
    NewRecord,
    Record,
    RecordType,
    SettingsV1,
    json_record,
)
from sadi.store.snapshot import SnapshotError
from sadi.store.wal import WalError, WalReader

_log = get_logger(__name__)

STATE_VERSION = 1
EditOp = Literal[
    "exclude", "include", "set_window", "override_input", "set_fit_window", "undo", "redo"
]
ANALYSIS_TARGET = "analysis"


class EventsError(BaseModel):
    """Base of replay failures; `hint` is shown in the UI."""

    model_config = ConfigDict(frozen=True)
    hint: str = ""


class EventsWal(EventsError):
    """The WAL is corrupt or unreadable; replay stops rather than skip anything."""

    error: WalError
    hint: str = "The recording is damaged; the verified part can still be viewed and exported."


class EventsGap(EventsError):
    """Records did not continue the base state's seq (a bug or a mismatched snapshot)."""

    expected: int
    found: int


class EventsSnapshot(EventsError):
    """A snapshot could not be consulted at all."""

    error: SnapshotError


class _Payload(BaseModel):
    """Base for event payloads: frozen, schema version `v`, unknown fields preserved."""

    model_config = ConfigDict(frozen=True, extra="allow")
    v: int = 1
    note: str | None = None


class PointWindow(_Payload):
    """The raw samples a captured point averages over (first/last raw seq and sample offsets)."""

    first_raw_seq: int
    last_raw_seq: int
    first_sample: int = 0
    last_sample: int = 0


class PointV1(_Payload):
    """A captured point; `computed` is for audit only, replay never trusts it."""

    point_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    phase: str
    window: PointWindow
    t_since_load_s: float | None = None
    drift_rate: float | None = None
    settled: bool = False
    forced_early: bool = False
    inputs: dict[str, Any] = {}
    computed: dict[str, Any] = {}
    # frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
    request_id: str | None = None  # client idempotency key: a replayed capture never records twice
    # frob:ticket 01M72VV7AGMWE3JE4MZFA8P5T6
    request_digest: str | None = None  # digest of the chosen inputs; None on older stored points


class EditV1(_Payload):
    """An append-only edit; undo/redo are edits whose `supersedes` names the edit_id affected."""

    target: str
    op: EditOp
    args: dict[str, Any] = {}
    edit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    supersedes: str | None = None


class PointEntry(BaseModel):
    """A POINT payload with the seq of its record."""

    model_config = ConfigDict(frozen=True)
    seq: int
    point: PointV1


class EditEntry(BaseModel):
    """An EDIT payload with the seq of its record."""

    model_config = ConfigDict(frozen=True)
    seq: int
    edit: EditV1


class SettingEntry(BaseModel):
    """A SETTINGS payload with the seq of its record."""

    model_config = ConfigDict(frozen=True)
    seq: int
    setting: SettingsV1


class MarkerEntry(BaseModel):
    """A MARKER payload with the seq of its record."""

    model_config = ConfigDict(frozen=True)
    seq: int
    marker: MarkerV1


class SkippedRecord(BaseModel):
    """A record replay could not interpret; it stays in the WAL untouched."""

    model_config = ConfigDict(frozen=True)
    seq: int
    type: int
    reason: str


class ReplayState(BaseModel):
    """Full event history up to `covers_seq`; the only thing a snapshot needs to store."""

    model_config = ConfigDict(frozen=True)
    v: int = STATE_VERSION
    covers_seq: int = 0
    record_count: int = 0
    points: tuple[PointEntry, ...] = ()
    edits: tuple[EditEntry, ...] = ()
    settings_log: tuple[SettingEntry, ...] = ()
    markers: tuple[MarkerEntry, ...] = ()
    skipped: tuple[SkippedRecord, ...] = ()

    def view(self) -> View:
        """Derive current values (points with edits applied, settings, analysis) from history."""
        return _derive(self)


class CurrentPoint(BaseModel):
    """A point with all active edits applied; `history` lists every edit that touched it."""

    model_config = ConfigDict(frozen=True)
    point: PointV1
    seq: int
    excluded: bool = False
    window: PointWindow
    inputs: dict[str, Any] = {}
    history: tuple[str, ...] = ()


class View(BaseModel):
    """Current state derived from a ReplayState."""

    model_config = ConfigDict(frozen=True)
    points: tuple[CurrentPoint, ...] = ()
    settings: dict[str, Any] = {}
    analysis: dict[str, Any] = {}
    active_edits: tuple[str, ...] = ()
    anomalies: tuple[str, ...] = ()


# ---- record builders ----------------------------------------------------------------------


def point_record(point: PointV1) -> NewRecord:
    """Build the POINT WAL record for `point`."""
    return json_record(RecordType.POINT, point)


def edit_record(edit: EditV1) -> NewRecord:
    """Build the EDIT WAL record for `edit` (also used for undo and redo)."""
    return json_record(RecordType.EDIT, edit)


def settings_record(setting: SettingsV1) -> NewRecord:
    """Build the SETTINGS WAL record for `setting`."""
    return json_record(RecordType.SETTINGS, setting)


def marker_record(marker: MarkerV1) -> NewRecord:
    """Build the MARKER WAL record for `marker`."""
    return json_record(RecordType.MARKER, marker)


# ---- replay -------------------------------------------------------------------------------


def _setting_key(s: SettingsV1) -> str:
    """Return the flat `scope/key` name of a setting."""
    return f"{s.scope}/{s.key}"


class _Acc:
    """Mutable accumulator used while folding records; frozen into a ReplayState."""

    def __init__(self, base: ReplayState) -> None:
        """Start from `base`."""
        self.covers_seq = base.covers_seq
        self.count = base.record_count
        self.points = list(base.points)
        self.edits = list(base.edits)
        self.settings = list(base.settings_log)
        self.markers = list(base.markers)
        self.skipped = list(base.skipped)

    def skip(self, rec: Record, reason: str) -> None:
        """Remember an uninterpretable record."""
        _log.warning("replay skipped seq=%d type=%#x: %s", rec.seq, rec.type, reason)
        self.skipped.append(SkippedRecord(seq=rec.seq, type=rec.type, reason=reason))

    def freeze(self) -> ReplayState:
        """Return the immutable state."""
        return ReplayState(
            covers_seq=self.covers_seq,
            record_count=self.count,
            points=tuple(self.points),
            edits=tuple(self.edits),
            settings_log=tuple(self.settings),
            markers=tuple(self.markers),
            skipped=tuple(self.skipped),
        )


def _apply(acc: _Acc, rec: Record) -> None:
    """Fold one record into the accumulator."""
    acc.covers_seq = rec.seq
    acc.count += 1
    if not rec.known:
        acc.skip(rec, "unknown record type")
        return
    rtype = RecordType(rec.type)
    if rtype not in (RecordType.POINT, RecordType.EDIT, RecordType.SETTINGS, RecordType.MARKER):
        return
    if not rec.flags & FLAG_JSON:
        acc.skip(rec, "payload is not JSON")
        return
    try:
        if rtype is RecordType.POINT:
            acc.points.append(
                PointEntry(seq=rec.seq, point=PointV1.model_validate_json(rec.payload))
            )
        elif rtype is RecordType.EDIT:
            acc.edits.append(EditEntry(seq=rec.seq, edit=EditV1.model_validate_json(rec.payload)))
        elif rtype is RecordType.SETTINGS:
            acc.settings.append(
                SettingEntry(seq=rec.seq, setting=SettingsV1.model_validate_json(rec.payload))
            )
        else:
            acc.markers.append(
                MarkerEntry(seq=rec.seq, marker=MarkerV1.model_validate_json(rec.payload))
            )
    except ValidationError as exc:
        acc.skip(rec, f"invalid {rtype.name} payload: {exc.error_count()} error(s)")


def replay(
    records: Iterable[Record],
    base: ReplayState | None = None,
    seal_seqs: Collection[int] = (),
) -> Result[ReplayState, EventsError]:
    """Fold verified records into a state; records at or below `base.covers_seq` are ignored.

    A seq jump is accepted only over seqs in `seal_seqs` (SEAL records consume a seq but are
    not data records); any other discontinuity is an `EventsGap`.
    """
    # frob:ticket 01M6WJMCTQ6M9SW2C3W6H5B4R2
    state = base or ReplayState()
    acc = _Acc(state)
    started = base is not None and base.covers_seq > 0
    for rec in records:
        if started and rec.seq <= state.covers_seq:
            continue
        if started:
            expected = acc.covers_seq + 1
            while expected in seal_seqs:
                expected += 1
            if rec.seq != expected:
                _log.error("replay gap: expected seq %d got %d", expected, rec.seq)
                return Err(EventsGap(expected=expected, found=rec.seq))
        started = True
        _apply(acc, rec)
    out = acc.freeze()
    _log.info(
        "replay done: covers_seq=%d records=%d points=%d edits=%d skipped=%d",
        out.covers_seq,
        out.record_count,
        len(out.points),
        len(out.edits),
        len(out.skipped),
    )
    return Ok(out)


def replay_wal(wal_dir: Path, base: ReplayState | None = None) -> Result[ReplayState, EventsError]:
    """Replay the verified WAL prefix (after `base`); corruption is an Err, never skipped."""
    start = (base.covers_seq + 1) if base else 1
    reader = WalReader(wal_dir)
    recs: list[Record] = []
    for item in reader.records(from_seq=start):
        if item.is_err:
            _log.error("replay of %s stopped by corruption: %s", wal_dir, item.danger_err)
            return Err(EventsWal(error=item.danger_err))
        recs.append(item.danger_ok)
    seals = reader.report.seal_seqs if reader.report else ()
    return replay(recs, base, seals)


def restore_state(snap: snapshot.SnapshotV1) -> ReplayState | None:
    """Rebuild a ReplayState from a snapshot payload; None (logged) when it does not fit."""
    try:
        state = ReplayState.model_validate(snap.state)
    except ValidationError as exc:
        _log.warning("snapshot state at %d is not a ReplayState: %s", snap.covers_seq, exc)
        return None
    if state.v != STATE_VERSION or state.covers_seq != snap.covers_seq:
        _log.warning("snapshot state version/covers mismatch at %d", snap.covers_seq)
        return None
    return state


def recover_state(session_dir: Path) -> Result[ReplayState, EventsError]:
    """Recover current state: newest valid snapshot plus WAL tail, else a full replay."""
    loaded = snapshot.load_latest_snapshot(session_dir)
    base: ReplayState | None = None
    if loaded.is_err:
        _log.warning("snapshot lookup failed (%s); replaying whole WAL", loaded.danger_err)
    elif loaded.danger_ok is not None:
        base = restore_state(loaded.danger_ok)
    return replay_wal(session_dir / "wal", base)


# ---- derivation ---------------------------------------------------------------------------


def _effective_edits(edits: tuple[EditEntry, ...], anomalies: list[str]) -> list[EditEntry]:
    """Resolve undo/redo: return the substantive edits that are active, in log order."""
    substantive: dict[str, EditEntry] = {}
    active: dict[str, bool] = {}
    undone_by: dict[str, str] = {}
    for entry in edits:
        e = entry.edit
        if e.op == "undo":
            if e.supersedes in substantive and active[e.supersedes]:
                active[e.supersedes] = False
                undone_by[e.edit_id] = e.supersedes
            else:
                anomalies.append(
                    f"seq {entry.seq}: undo of unknown or inactive edit {e.supersedes}"
                )
        elif e.op == "redo":
            target = undone_by.get(e.supersedes or "")
            if target is not None and not active[target]:
                active[target] = True
            else:
                anomalies.append(
                    f"seq {entry.seq}: redo of unknown or inactive undo {e.supersedes}"
                )
        elif e.edit_id in substantive:
            anomalies.append(f"seq {entry.seq}: duplicate edit_id {e.edit_id} ignored")
        else:
            substantive[e.edit_id] = entry
            active[e.edit_id] = True
    return [en for eid, en in substantive.items() if active[eid]]


def _apply_edit(
    entry: EditEntry,
    points: dict[str, dict[str, Any]],
    analysis: dict[str, Any],
    anomalies: list[str],
) -> None:
    """Apply one active edit to the mutable derivation tables."""
    e = entry.edit
    if e.target == ANALYSIS_TARGET:
        if e.op == "set_fit_window":
            analysis["fit_window"] = dict(e.args)
        else:
            anomalies.append(f"seq {entry.seq}: op {e.op} not valid on analysis")
        return
    p = points.get(e.target)
    if p is None:
        anomalies.append(f"seq {entry.seq}: edit of unknown point {e.target}")
        return
    p["history"].append(e.edit_id)
    if e.op == "exclude":
        p["excluded"] = True
    elif e.op == "include":
        p["excluded"] = False
    elif e.op == "set_window":
        try:
            p["window"] = PointWindow.model_validate({**p["window"].model_dump(), **e.args})
        except ValidationError:
            anomalies.append(f"seq {entry.seq}: set_window args invalid")
    elif e.op == "override_input":
        p["inputs"].update(e.args)
    else:
        anomalies.append(f"seq {entry.seq}: op {e.op} not valid on a point")


def _derive(state: ReplayState) -> View:
    """Fold history into the current view; pure and deterministic."""
    anomalies: list[str] = []
    table: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for pe in state.points:
        pid = pe.point.point_id
        if pid in table:
            anomalies.append(f"seq {pe.seq}: duplicate point_id {pid} ignored")
            continue
        order.append(pid)
        table[pid] = {
            "entry": pe,
            "excluded": False,
            "window": pe.point.window,
            "inputs": dict(pe.point.inputs),
            "history": [],
        }
    analysis: dict[str, Any] = {}
    active = _effective_edits(state.edits, anomalies)
    for entry in active:
        _apply_edit(entry, table, analysis, anomalies)
    settings = {_setting_key(s.setting): s.setting.value for s in state.settings_log}
    points = tuple(
        CurrentPoint(
            point=table[pid]["entry"].point,
            seq=table[pid]["entry"].seq,
            excluded=table[pid]["excluded"],
            window=table[pid]["window"],
            inputs=table[pid]["inputs"],
            history=tuple(table[pid]["history"]),
        )
        for pid in order
    )
    return View(
        points=points,
        settings=settings,
        analysis=analysis,
        active_edits=tuple(en.edit.edit_id for en in active),
        anomalies=tuple(anomalies),
    )
