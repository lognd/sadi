"""Session service: the one place REST handlers reach the session, WAL and wizard layers.

Handlers stay thin; this wraps `create_session_in_held_root` / `resume_session_in_held_root`
(the app already holds the data-root lock), a `WriterHandle` and the core `Wizard`. Every
accepted write is appended to the WAL and made durable before the call returns; undo and
redo are compensating edits, so nothing is ever deleted or overwritten.
"""

# frob:ticket 01M6W7R3XY1B0BF689RX3H80G2

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel
from typani import Err, Ok, Result, propagate

from sadi.core.lab import LabId, LabModule, StepId
from sadi.core.point_inputs import (
    PointMeta,
    build_point,
    check_ranges,
    check_window,
    parse_inputs,
)
from sadi.core.registry import LabRegistry
from sadi.core.wizard import Command, History, Wizard, WizardError, WizardState
from sadi.labs.lctt.guidance import Phase
from sadi.logging_setup import get_logger
from sadi.server.routes.problem import (
    ApiProblem,
    conflict,
    from_model,
    from_sadi,
    from_wizard,
    not_found,
)
from sadi.server.run_phase import check_transition, fold_phase, next_allowed, phase_record
from sadi.server.schemas import (
    CaptureBody,
    Committed,
    EditBody,
    LabInfo,
    PointView,
    RunPhaseView,
    SessionCreate,
    SessionInfo,
    SessionSummary,
)
from sadi.store.events import EventsWal, ReplayState, recover_state
from sadi.store.incremental import IncrementalReplay
from sadi.store.manifest import read_manifest
from sadi.store.records import FLAG_JSON, NewRecord, RecordType
from sadi.store.session import (
    SESSIONS_DIRNAME,
    SessionHandle,
    SessionMeta,
    create_session_in_held_root,
    read_lock_holder,
    resume_session_in_held_root,
    session_is_synthetic,
)
from sadi.store.snapshot import SnapshotCadence, write_snapshot
from sadi.store.spill import write_spill
from sadi.store.wal import WalReader
from sadi.store.writer_thread import WriterHandle
from sadi.synthetic.provenance import REAL, SYNTHETIC, DataProvenance

_log = get_logger(__name__)

#: Seconds a write waits for fsync before the request fails (data stays queued, not lost).
DURABLE_TIMEOUT_S = 10.0

_T = TypeVar("_T")


@dataclass(frozen=True)
class ClosedSession:
    """A session read straight from disk for review: nothing about it can be written."""

    path: Path
    lab: LabModule
    views: list[PointView]
    provenance: DataProvenance
    # frob:ticket 01M727965F98C8FB295P7A7FRS
    torn_tail: str | None = None  # "segment/offset" when only the verified prefix was read


@dataclass
class _Open:
    """The one open session: its handle, writer, lab and wizard."""

    handle: SessionHandle
    writer: WriterHandle
    lab: LabModule
    wizard: Wizard
    # frob:ticket 01M6X3AVGVT23M1E9V82RWJ137
    replayer: IncrementalReplay = field(init=False)
    # frob:ticket 01M71YY12XP2ZDM402A00A7RJW
    cadence: SnapshotCadence = field(default_factory=SnapshotCadence)
    # frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
    requests: dict[str, int] = field(default_factory=dict)  # capture request_id -> submitted seq

    def __post_init__(self) -> None:
        """Attach the incremental replay cache for this session's directory."""
        self.replayer = IncrementalReplay(self.handle.path)


#: Record types after which a snapshot is always taken (data-safety.md 9.1 cadence).
_SNAPSHOT_FORCING = frozenset({int(RecordType.POINT), int(RecordType.EDIT)})

# frob:ticket 01M6WTCAA5WR1VD7H7ES7757MP
_FOLD_TYPES = frozenset(
    {
        int(RecordType.POINT),
        int(RecordType.EDIT),
        int(RecordType.SETTINGS),
        int(RecordType.MARKER),
        int(RecordType.NOTE),
    }
)


def _from_store(err: BaseModel) -> ApiProblem:
    """Map a store-layer error to its API problem (shared by every propagation site)."""
    return from_model(err, "store")


@propagate
def _fold_parent(parent: Path, writer: WriterHandle) -> Result[int, ApiProblem]:
    """Append the parent's state records to `writer` in order and wait until durable.

    Only POINT/EDIT/SETTINGS/MARKER/NOTE records are copied (raw capture data stays in the parent);
    relative order is kept so replay of the child equals replay of the parent. Returns the count.
    """
    last = 0
    count = 0
    for item in WalReader(parent / "wal").records():
        if item.is_err:
            _log.error("fold of %s stopped by corruption: %s", parent.name, item.danger_err)
            return Err(from_model(EventsWal(error=item.danger_err), "store"))
        rec = item.danger_ok
        if rec.type not in _FOLD_TYPES:
            continue
        sub = writer.submit(NewRecord(type=rec.type, payload=rec.payload, flags=rec.flags))
        last = sub.map_err(_from_store).unwrap()
        count += 1
    if last:
        durable = writer.wait_durable(last, DURABLE_TIMEOUT_S)
        durable.map_err(_from_store).unwrap()
    _log.info("folded %d state records from %s", count, parent.name)
    return Ok(count)


def _unprocessable(code: str, detail: str, hint: str) -> ApiProblem:
    """A 422 for rejected input; the WAL is untouched."""
    return ApiProblem(
        type=f"urn:sadi:error:input:{code}",
        title=code.replace("_", " "),
        status=422,
        detail=detail,
        hint=hint,
    )


def _phase_view(phase: Phase | None) -> RunPhaseView:
    """Project a recorded phase into the REST view."""
    return RunPhaseView(phase=phase, next_phase=next_allowed(phase))


class SessionService:
    """Owns the single open session of this server process; calls are serialized by a lock."""

    def __init__(self, data_root: Path, labs: LabRegistry, synthetic: bool = False) -> None:
        """Serve sessions under `data_root` (lock held by the app) for the registered `labs`.

        `synthetic` makes every session this service creates synthetic and refuses to resume a
        real one (and vice versa): the two data modes are never mixed.
        """
        self._synthetic = synthetic  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
        self._root = data_root
        self._labs = labs
        self._lock = threading.RLock()
        self._open: _Open | None = None
        self._on_open: Callable[[WriterHandle, Path], None] | None = None
        self._before_close: Callable[[], None] | None = None
        # frob:ticket 01M724AKWJV8BRNRR3Q43553VR
        self._capture_gate: Callable[[], str | None] | None = None
        # frob:ticket 01M724E09H9X4DDW9ATK14JQ5C
        self._finisher: Callable[[], Result[int, object]] | None = None
        self._acq_state: Callable[[], tuple[str | None, str | None]] | None = None

    def provenance(self) -> DataProvenance:
        """The data provenance every payload of this service carries (real unless synthetic)."""
        return SYNTHETIC if self._synthetic else REAL

    def set_hooks(
        self,
        on_open: Callable[[WriterHandle, Path], None],
        before_close: Callable[[], None],
    ) -> None:
        """Register live-acquisition hooks: after a session opens, and before its writer closes."""
        self._on_open = on_open
        self._before_close = before_close

    # frob:ticket 01M724AKWJV8BRNRR3Q43553VR
    def set_capture_gate(self, gate: Callable[[], str | None]) -> None:
        """Register a gate returning a hint while capture is blocked (no device), else None."""
        self._capture_gate = gate

    # frob:ticket 01M724E09H9X4DDW9ATK14JQ5C
    def set_acquisition(
        self,
        finish: Callable[[], Result[int, object]],
        state: Callable[[], tuple[str | None, str | None]],
    ) -> None:
        """Register the live-acquisition finish action and its (stop_reason, fault) reader."""
        self._finisher = finish
        self._acq_state = state

    # frob:ticket 01M724E09H9X4DDW9ATK14JQ5C
    def finish_acquisition(self) -> bool:
        """Drain raw blocks into the WAL and stop streaming; True when it ended cleanly or is unwired.

        Idempotent and data-safe: nothing is deleted or truncated, the session stays open, and a
        fault is logged and kept for the status API, never raised into the request.
        """
        if self._finisher is None:
            return True
        done = self._finisher()
        if done.is_err:
            _log.error("finish_acquisition faulted (recorded blocks remain): %s", done.danger_err)
            return False
        _log.info("finish_acquisition ok: %d trailing blocks saved", done.danger_ok)
        return True

    # frob:ticket 01M724E09H9X4DDW9ATK14JQ5C
    def acquisition_state(self) -> tuple[str | None, str | None]:
        """(stop_reason, fault detail) of raw streaming; (None, None) when no live acquisition."""
        return self._acq_state() if self._acq_state is not None else (None, None)

    # ---- discovery --------------------------------------------------------------------

    def labs(self) -> list[LabInfo]:
        """List the registered labs."""
        out: list[LabInfo] = []
        for lab_id in self._labs.ids():
            got = self._labs.get(LabId(lab_id))
            if got.is_ok:
                out.append(LabInfo(id=lab_id, title=got.danger_ok.title))
        return out

    def list_sessions(self) -> list[SessionSummary]:
        """List session versions on disk by reading manifests only (nothing is written)."""
        base = self._root / SESSIONS_DIRNAME
        out: list[SessionSummary] = []
        for d in sorted(base.iterdir()) if base.is_dir() else []:
            mf = read_manifest(d)
            if mf.is_err or mf.danger_ok is None:
                _log.warning("session %s has no readable manifest; listed as unknown", d.name)
                continue
            m = mf.danger_ok
            out.append(
                SessionSummary(
                    name=d.name,
                    family=m.family,
                    version=m.version,
                    lab=m.lab_module,
                    state=m.state,
                    parent=m.parent,
                    provenance=SYNTHETIC if session_is_synthetic(d) else REAL,
                )
            )
        return out

    # frob:ticket 01M724AKTJNNRY06637VBQ0A3E
    @propagate
    def read_closed(self, name: str) -> Result[ClosedSession, ApiProblem]:
        """Read session `name` from disk without a writer, lock, version, WAL append or device.

        Refuses the session this service has open and one whose writer is alive elsewhere;
        a corrupt log is a problem too, but a torn tail (crash) exports the verified prefix. Nothing under the session directory is modified.
        """
        with self._lock:
            if self._open is not None and self._open.handle.path.name == name:
                return Err(
                    conflict(
                        "session_open",
                        f"{name} is the open session and is still being written",
                        "Close it first, or use the export on the open session.",
                    )
                )
            path = self._root / SESSIONS_DIRNAME / name
            if not name or "/" in name or "\\" in name or name.startswith(".") or not path.is_dir():
                return Err(not_found(name, "Pick a session from the list of sessions."))
            mf = read_manifest(path)
            if mf.is_err or mf.danger_ok is None:
                _log.error("read_closed %s: manifest unreadable", name)
                return Err(
                    conflict(
                        "session_unreadable",
                        f"{name} has no readable manifest",
                        "Run the Doctor to inspect the session; nothing was changed.",
                    )
                )
            holder, alive = read_lock_holder(path)
            if mf.danger_ok.state == "open" and alive:
                _log.warning("read_closed %s: writer alive (%s)", name, holder)
                return Err(
                    conflict(
                        "session_open",
                        f"{name} is being written by a running process",
                        "Close it there first; nothing was changed.",
                    )
                )
            lab = self._labs.get(LabId(mf.danger_ok.lab_module)).map_err(from_sadi).unwrap()
            scan = WalReader.scan(path / "wal")  # read-only verification of the whole log
            if scan.is_err:
                detail = repr(scan.danger_err)
                _log.error("read_closed %s: WAL not clean: %s", name, detail)
                return Err(
                    conflict(
                        "session_corrupt",
                        f"{name} has a damaged or incomplete log: {detail}"[:300],
                        "Run the Doctor to inspect the session; nothing was changed.",
                    )
                )
            tail = scan.danger_ok.tail  # frob:ticket 01M727965F98C8FB295P7A7FRS
            torn = None if tail is None else f"{tail.segment}/{tail.offset}"
            if tail is not None:
                # A torn tail is the normal result of a crash: export the verified prefix.
                _log.warning(
                    "read_closed %s: torn tail at %s; exporting verified prefix", name, torn
                )
            state = recover_state(path)
            if state.is_err:
                _log.error("read_closed %s: replay failed: %s", name, state.danger_err)
                return Err(
                    conflict(
                        "session_corrupt",
                        f"{name} could not be replayed: {state.danger_err!r}"[:300],
                        "Run the Doctor to inspect the session; nothing was changed.",
                    )
                )
            views = [PointView.of(p) for p in state.danger_ok.view().points]
            prov = SYNTHETIC if session_is_synthetic(path) else REAL
            _log.info("read_closed %s: %d points (read-only)", name, len(views))
            return Ok(
                ClosedSession(path=path, lab=lab, views=views, provenance=prov, torn_tail=torn)
            )

    # ---- lifecycle --------------------------------------------------------------------

    @propagate
    def create(self, req: SessionCreate) -> Result[SessionInfo, ApiProblem]:
        """Create a new session family for the requested lab and open it for writing."""
        with self._lock:
            busy = self._refuse_if_open()
            if busy is not None:
                return Err(busy)
            lab = self._labs.get(LabId(req.lab)).map_err(from_sadi).unwrap()
            meta = SessionMeta(
                slug=req.slug, lab_module=req.lab, specimen=req.specimen, synthetic=self._synthetic
            )
            made = create_session_in_held_root(self._root, meta)
            return self._attach(made.map_err(_from_store).unwrap(), lab)

    @propagate
    def resume(self, name: str) -> Result[SessionInfo, ApiProblem]:
        """Open the next version of session `name`; the parent is never modified.

        The parent's points, edits, settings and wizard markers are copied (in order, as new
        WAL records) into the child's WAL before it is returned; the parent stays untouched.
        """
        with self._lock:
            busy = self._refuse_if_open()
            if busy is not None:
                return Err(busy)
            parent = self._root / SESSIONS_DIRNAME / name
            if "/" in name or "\\" in name or not parent.is_dir():
                return Err(not_found(name, "Pick a session from the list of sessions."))
            mf = read_manifest(parent)
            lab_id = mf.danger_ok.lab_module if mf.is_ok and mf.danger_ok is not None else ""
            lab = self._labs.get(LabId(lab_id)).map_err(from_sadi).unwrap()
            made = resume_session_in_held_root(parent, synthetic=self._synthetic)
            return self._attach(made.map_err(_from_store).unwrap(), lab, fold_from=parent)

    @propagate
    def close(self) -> Result[None, ApiProblem]:
        """Drain the writer and close the open session (manifest written atomically)."""
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            self.finish_acquisition()  # frob:ticket 01M724E09H9X4DDW9ATK14JQ5C
            if self._before_close is not None:
                self._before_close()
            closed = cur.writer.close()
            if closed.is_ok:
                self._open = None
                self._snapshot(cur, forced=True)  # frob:ticket 01M71YY12XP2ZDM402A00A7RJW
            else:
                # frob:ticket 01M726PZKE3CYNC5NABZC56HT2
                _log.error("writer close failed: %s", closed.danger_err)
                kept = self._spill_failed(cur)
                if kept is not None:
                    return Err(kept)
                self._open = None
                cur.handle.close(state="incomplete")
                return Err(from_model(closed.danger_err, "store"))
            shut = cur.handle.close()
            shut.map_err(_from_store).unwrap()
            _log.info("session %s closed", cur.handle.path.name)
            return Ok(None)

    # frob:ticket 01M726PZKE3CYNC5NABZC56HT2
    def _spill_failed(self, cur: _Open) -> ApiProblem | None:
        """Spill a failed writer's undurable records; return a 409 when they could not be saved.

        None means nothing was lost (spilled to disk, or there was nothing undurable); on a
        409 the writer stays open in memory so the user can fix the disk and retry Close.
        """
        pending = cur.writer.undurable_records()
        if not pending:
            return None
        spilled = write_spill(pending, uuid.UUID(cur.handle.manifest.session_uuid), self._root)
        if spilled.is_ok:
            _log.warning(
                "failed writer: %d undurable record(s) spilled to %s; import_all_spills "
                "recovers them at next start",
                len(pending),
                [str(p) for p in spilled.danger_ok],
            )
            return None
        _log.critical(
            "failed writer: %d undurable record(s) could NOT be spilled (%s); kept in memory",
            len(pending),
            spilled.danger_err.attempts,
        )
        return conflict(
            "undurable_records",
            f"{len(pending)} unsaved record(s) could not be written to any spill location",
            "Free disk space or reattach the drive, then press Close session again.",
        )

    def shutdown(self) -> None:
        """Close any open session at app shutdown; failures are logged, never raised."""
        if self._open is not None:
            res = self.close()
            if res.is_err:
                _log.error("shutdown close failed: %s", res.danger_err)

    def info(self) -> Result[SessionInfo, ApiProblem]:
        """Describe the open session."""
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            return Ok(self._info(cur))

    # frob:ticket 01M6WVADB5YKXAVC43CQNBQVJW
    def session_path(self) -> Result[Path, ApiProblem]:
        """Return the open session's directory (read-only use: replaying its log)."""
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            return Ok(cur.handle.path)

    # ---- wizard -----------------------------------------------------------------------

    def wizard_state(self) -> Result[WizardState, ApiProblem]:
        """Derive the rail and current step from the log."""
        return self._read(lambda cur, rp: cur.wizard.state(rp))

    def complete(self, step: str) -> Result[Committed, ApiProblem]:
        """Mark the current step done, unless the lab's quality gate for it fails (422)."""
        with self._lock:
            cur = self._open
            if cur is not None:
                rp = self._replay(cur)
                if rp.is_ok and cur.wizard.complete(rp.danger_ok, StepId(step)).is_ok:
                    why = cur.wizard.not_ready(rp.danger_ok, StepId(step))
                    if why is not None:
                        return Err(_unprocessable("step_quality_gate", why, why))
            return self._act(lambda cur, rp: cur.wizard.complete(rp, StepId(step)))

    def skip(self, step: str) -> Result[Committed, ApiProblem]:
        """Explicitly skip the current step."""
        return self._act(lambda cur, rp: cur.wizard.skip(rp, StepId(step)))

    def revert(self, step: str | None) -> Result[Committed, ApiProblem]:
        """Reopen the most recently finished step."""
        return self._act(
            lambda cur, rp: cur.wizard.revert(rp, None if step is None else StepId(step))
        )

    # ---- points -----------------------------------------------------------------------

    def points(self) -> Result[list[PointView], ApiProblem]:
        """List captured points with edits applied (excluded points included, flagged)."""
        return self._read(lambda _cur, rp: [PointView.of(p) for p in rp.view().points])

    @propagate
    def capture(self, body: CaptureBody) -> Result[Committed, ApiProblem]:
        """Validate typed inputs and window (nothing logged on rejection), then append a POINT.

        A `request_id` makes the call idempotent: a replay returns the existing commit and
        never records a second point.
        """
        # frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
        if body.request_id is not None:
            existing = self._existing_capture(body.request_id).unwrap()
            if existing is not None:
                return Ok(existing)
        # frob:ticket 01M724AKWJV8BRNRR3Q43553VR
        blocked = None if self._capture_gate is None else self._capture_gate()
        if blocked is not None:
            _log.warning("capture refused: %s", blocked)
            return Err(conflict("no_device", blocked, blocked))
        parsed = parse_inputs(body.phase, body.inputs)
        parsed_ok = parsed.map_err(
            lambda detail: _unprocessable(
                "missing", detail, "Fill in the required field before continuing."
            )
        ).unwrap()
        check_ranges(parsed_ok).map_err(
            lambda detail: _unprocessable(
                "out_of_range", detail, "Enter the value in the unit named in the message."
            )
        ).unwrap()
        check_window(body.window).map_err(
            lambda detail: _unprocessable(
                "bad_window", detail, "Capture from the live trace so the window is recorded."
            )
        ).unwrap()
        meta = PointMeta(
            t_since_load_s=body.t_since_load_s,
            drift_rate=body.drift_rate,
            settled=body.settled,
            forced_early=body.forced_early,
        )
        point = build_point(parsed_ok, body.window, meta).model_copy(
            update={"request_id": body.request_id}
        )
        return self._act(lambda cur, rp: cur.wizard.capture(rp, point), request_id=body.request_id)

    # frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
    @propagate
    def _existing_capture(self, request_id: str) -> Result[Committed | None, ApiProblem]:
        """The commit of an earlier capture with this `request_id`, else None (nothing written).

        Covers both a point already in the replay and one submitted whose durability wait
        timed out: the latter is waited on again instead of being recorded twice.
        """
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            rp = self._replay(cur).unwrap()
            seq = cur.requests.get(request_id)
            if seq is None:
                seq = next(
                    (p.seq for p in rp.view().points if p.point.request_id == request_id), None
                )
            if seq is None:
                return Ok(None)
            cur.writer.wait_durable(seq, DURABLE_TIMEOUT_S).map_err(_from_store).unwrap()
            after = self._replay(cur).unwrap()
            _log.info("capture replay request_id=%s -> existing seq %d", request_id, seq)
            return Ok(
                Committed(
                    seq=seq,
                    summary="captured (replayed request)",
                    wizard=cur.wizard.state(after),
                    history=cur.wizard.history(after),
                )
            )

    def edit(self, target: str, body: EditBody) -> Result[Committed, ApiProblem]:
        """Append an edit of `target`; the original value stays in the log."""
        return self._act(lambda cur, rp: cur.wizard.edit(rp, target, body.op, body.args))

    def undo(self) -> Result[Committed, ApiProblem]:
        """Undo the latest action via a compensating edit."""
        return self._act(lambda cur, rp: cur.wizard.undo(rp))

    def redo(self) -> Result[Committed, ApiProblem]:
        """Redo the latest undone action."""
        return self._act(lambda cur, rp: cur.wizard.redo(rp))

    def history(self) -> Result[History, ApiProblem]:
        """Return the undo and redo stacks."""
        return self._read(lambda cur, rp: cur.wizard.history(rp))

    # ---- notes ------------------------------------------------------------------------

    # frob:ticket 01M6WTC9ZQWCTYX5WADMDHYBZ1
    @propagate
    def append_note(self, payload: str) -> Result[int, ApiProblem]:
        """Append a JSON NOTE record and return its seq once durable (never overwrites)."""
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            note = NewRecord(
                type=int(RecordType.NOTE), payload=payload.encode("utf-8"), flags=FLAG_JSON
            )
            sub = cur.writer.submit(note)
            last = sub.map_err(_from_store).unwrap()
            durable = cur.writer.wait_durable(last, DURABLE_TIMEOUT_S)
            durable.map_err(_from_store).unwrap()
            _log.info("note appended at seq %d (%d bytes)", last, len(payload))
            return Ok(last)

    # frob:ticket 01M6WTC9ZQWCTYX5WADMDHYBZ1
    # frob:ticket 01M6X465ZVYG4B9Y79QAZ8KDXT
    def notes(self) -> Result[list[str], ApiProblem]:
        """Return every JSON NOTE payload of the open session in WAL order."""
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            got = cur.replayer.notes()  # typani: ignore[TYP001]
            if got.is_err:
                _log.error("note scan stopped by corruption: %s", got.danger_err)
                return Err(from_model(got.danger_err, "store"))
            return Ok(list(got.danger_ok))

    # ---- run phase --------------------------------------------------------------------

    # frob:ticket 01M6XAKF5AK7FCJNBHPM62NYRS
    def run_phase(self) -> Result[RunPhaseView, ApiProblem]:
        """The recorded guided-run phase (None for old sessions) and the next allowed one."""
        return self._read(lambda _cur, rp: _phase_view(fold_phase(rp.markers)))

    # frob:ticket 01M6XAKF5AK7FCJNBHPM62NYRS
    @propagate
    def enter_phase(self, phase: Phase) -> Result[RunPhaseView, ApiProblem]:
        """Record entry into `phase` (append-only MARKER, durable); only the next phase is legal."""
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            rp = self._replay(cur)
            now = fold_phase(rp.unwrap().markers)
            ok = check_transition(now, phase)
            if ok.is_err:
                refusal = ok.danger_err
                _log.info("run phase %s refused: %s", phase, refusal.reason)
                return Err(
                    conflict(
                        "bad_phase_transition",
                        f"cannot enter {phase.value} from "
                        f"{'no phase' if now is None else now.value}: {refusal.reason}",
                        "Phases advance in order: calibrate, elastic, plastic.",
                    )
                )
            sub = cur.writer.submit(phase_record(phase))
            last = sub.map_err(_from_store).unwrap()
            durable = cur.writer.wait_durable(last, DURABLE_TIMEOUT_S)
            durable.map_err(_from_store).unwrap()
            _log.info("run phase %s -> %s at seq %d", now, phase, last)
            return Ok(_phase_view(phase))

    # ---- internals --------------------------------------------------------------------

    def _none_open(self) -> ApiProblem:
        """The problem for a call that needs an open session."""
        return conflict(
            "no_open_session", "no session is open", "Create or resume a session first."
        )

    def _refuse_if_open(self) -> ApiProblem | None:
        """A problem when a session is already open (one writer at a time), else None."""
        if self._open is None:
            return None
        return conflict(
            "session_open",
            f"{self._open.handle.path.name} is open",
            "Close the open session before starting or resuming another.",
        )

    def _info(self, cur: _Open) -> SessionInfo:
        """Build the SessionInfo of `cur`."""
        m = cur.handle.manifest
        return SessionInfo(
            name=cur.handle.path.name,
            lab=m.lab_module,
            parent=m.parent,
            parent_last_seq=m.parent_last_seq,
            durable_seq=cur.writer.durable_seq,
            provenance=self.provenance(),
        )

    def _attach(
        self, handle: SessionHandle, lab: LabModule, fold_from: Path | None = None
    ) -> Result[SessionInfo, ApiProblem]:
        """Open the writer and wizard for a new version; roll the handle back on error.

        With `fold_from` (a resume parent) its state records are copied in and made durable
        first; any failure leaves the child marked incomplete and never opens it.
        """
        wiz = Wizard.create(lab.steps())
        if wiz.is_err:
            handle.close(state="incomplete")
            return Err(from_wizard(wiz.danger_err))
        opened = WriterHandle.open(
            handle.path / "wal", uuid.UUID(handle.manifest.session_uuid), first_seq=1
        )
        if opened.is_err:
            handle.close(state="incomplete")
            return Err(from_model(opened.danger_err, "store"))
        if fold_from is not None:
            folded = _fold_parent(fold_from, opened.danger_ok)
            if folded.is_err:
                opened.danger_ok.close()
                handle.close(state="incomplete")
                return Err(folded.danger_err)
        self._open = _Open(handle, opened.danger_ok, lab, wiz.danger_ok)
        _log.info("session %s open (lab %s)", handle.path.name, lab.id)
        if self._on_open is not None:
            self._on_open(opened.danger_ok, handle.path)
        return Ok(self._info(self._open))

    # frob:ticket 01M71YY12XP2ZDM402A00A7RJW
    def _snapshot(self, cur: _Open, forced: bool) -> None:
        """Best-effort atomic snapshot of the live state (no SNAPSHOT_REF); failures are only logged."""
        replayed = cur.replayer.state()
        if replayed.is_err:
            _log.warning("snapshot skipped, replay failed: %s", replayed.danger_err)
            return
        state = replayed.danger_ok
        if not cur.cadence.due(state.covers_seq, forced):
            return
        wrote = write_snapshot(
            cur.handle,
            state,
            state.covers_seq,
            prefix_hash_hex=cur.replayer.prefix_hash_at(state.covers_seq),
            lab_module=str(cur.lab.id),
        )
        if wrote.is_err:
            _log.warning("snapshot at seq %d failed: %s", state.covers_seq, wrote.danger_err)
            return
        cur.cadence.written(state.covers_seq)

    # frob:ticket 01M6X3AVGVT23M1E9V82RWJ137
    @propagate
    def _replay(self, cur: _Open) -> Result[ReplayState, ApiProblem]:
        """Return the current ReplayState (incrementally cached; equal to a full replay)."""
        got = cur.replayer.state()
        return Ok(got.map_err(_from_store).unwrap())

    @propagate
    def _read(self, fn: Callable[[_Open, ReplayState], _T]) -> Result[_T, ApiProblem]:
        """Run a read-only projection over the replayed state."""
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            rp = self._replay(cur)
            return Ok(fn(cur, rp.unwrap()))

    @propagate
    def _act(
        self,
        fn: Callable[[_Open, ReplayState], Result[Command, WizardError]],
        request_id: str | None = None,
    ) -> Result[Committed, ApiProblem]:
        """Run a wizard command, append its records, wait for durability, return the new state.

        With a `request_id` the last submitted seq is remembered before the durability wait,
        so a retry after a timeout finds the in-flight record instead of writing another.
        """
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            rp = self._replay(cur)
            cmd = fn(cur, rp.unwrap())
            seq = 0
            for rec in cmd.map_err(from_wizard).unwrap().records:
                sub = cur.writer.submit(rec)
                seq = sub.map_err(_from_store).unwrap()
            if request_id is not None:
                cur.requests[request_id] = seq
            durable = cur.writer.wait_durable(seq, DURABLE_TIMEOUT_S)
            durable.map_err(_from_store).unwrap()
            after = self._replay(cur).unwrap()
            self._snapshot(
                cur, forced=any(r.type in _SNAPSHOT_FORCING for r in cmd.danger_ok.records)
            )
            _log.info("committed seq %d: %s", seq, cmd.danger_ok.summary)
            return Ok(
                Committed(
                    seq=seq,
                    summary=cmd.danger_ok.summary,
                    wizard=cur.wizard.state(after),
                    history=cur.wizard.history(after),
                )
            )
