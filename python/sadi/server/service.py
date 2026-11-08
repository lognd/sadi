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
from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from typani import Err, Ok, Result

from sadi.core.lab import LabId, LabModule, StepId
from sadi.core.point_inputs import PointMeta, build_point, parse_inputs
from sadi.core.registry import LabRegistry
from sadi.core.wizard import Command, History, Wizard, WizardError, WizardState
from sadi.logging_setup import get_logger
from sadi.server.routes.problem import (
    ApiProblem,
    conflict,
    from_model,
    from_sadi,
    from_wizard,
    not_found,
)
from sadi.server.schemas import (
    CaptureBody,
    Committed,
    EditBody,
    LabInfo,
    PointView,
    SessionCreate,
    SessionInfo,
    SessionSummary,
)
from sadi.store.events import EventsWal, ReplayState, recover_state
from sadi.store.manifest import read_manifest
from sadi.store.session import (
    SESSIONS_DIRNAME,
    SessionHandle,
    SessionMeta,
    create_session_in_held_root,
    resume_session_in_held_root,
)
from sadi.store.records import NewRecord, RecordType
from sadi.store.wal import WalReader
from sadi.store.writer_thread import WriterHandle

_log = get_logger(__name__)

#: Seconds a write waits for fsync before the request fails (data stays queued, not lost).
DURABLE_TIMEOUT_S = 10.0

_T = TypeVar("_T")


@dataclass
class _Open:
    """The one open session: its handle, writer, lab and wizard."""

    handle: SessionHandle
    writer: WriterHandle
    lab: LabModule
    wizard: Wizard


# frob:ticket 01M6WTCAA5WR1VD7H7ES7757MP
_FOLD_TYPES = frozenset(
    {int(RecordType.POINT), int(RecordType.EDIT), int(RecordType.SETTINGS), int(RecordType.MARKER)}
)


def _fold_parent(parent: Path, writer: WriterHandle) -> Result[int, ApiProblem]:
    """Append the parent's state records to `writer` in order and wait until durable.

    Only POINT/EDIT/SETTINGS/MARKER records are copied (raw capture data stays in the parent);
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
        if sub.is_err:
            return Err(from_model(sub.danger_err, "store"))
        last = sub.danger_ok
        count += 1
    if last:
        durable = writer.wait_durable(last, DURABLE_TIMEOUT_S)
        if durable.is_err:
            return Err(from_model(durable.danger_err, "store"))
    _log.info("folded %d state records from %s", count, parent.name)
    return Ok(count)


class SessionService:
    """Owns the single open session of this server process; calls are serialized by a lock."""

    def __init__(self, data_root: Path, labs: LabRegistry) -> None:
        """Serve sessions under `data_root` (lock held by the app) for the registered `labs`."""
        self._root = data_root
        self._labs = labs
        self._lock = threading.RLock()
        self._open: _Open | None = None

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
                )
            )
        return out

    # ---- lifecycle --------------------------------------------------------------------

    def create(self, req: SessionCreate) -> Result[SessionInfo, ApiProblem]:
        """Create a new session family for the requested lab and open it for writing."""
        with self._lock:
            busy = self._refuse_if_open()
            if busy is not None:
                return Err(busy)
            lab = self._labs.get(LabId(req.lab))
            if lab.is_err:
                return Err(from_sadi(lab.danger_err))
            meta = SessionMeta(slug=req.slug, lab_module=req.lab, specimen=req.specimen)
            made = create_session_in_held_root(self._root, meta)
            if made.is_err:
                return Err(from_model(made.danger_err, "store"))
            return self._attach(made.danger_ok, lab.danger_ok)

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
            lab = self._labs.get(LabId(lab_id))
            if lab.is_err:
                return Err(from_sadi(lab.danger_err))
            made = resume_session_in_held_root(parent)
            if made.is_err:
                return Err(from_model(made.danger_err, "store"))
            return self._attach(made.danger_ok, lab.danger_ok, fold_from=parent)

    def close(self) -> Result[None, ApiProblem]:
        """Drain the writer and close the open session (manifest written atomically)."""
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            closed = cur.writer.close()
            self._open = None
            if closed.is_err:
                _log.error("writer close failed: %s", closed.danger_err)
                cur.handle.close(state="incomplete")
                return Err(from_model(closed.danger_err, "store"))
            shut = cur.handle.close()
            if shut.is_err:
                return Err(from_model(shut.danger_err, "store"))
            _log.info("session %s closed", cur.handle.path.name)
            return Ok(None)

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

    # ---- wizard -----------------------------------------------------------------------

    def wizard_state(self) -> Result[WizardState, ApiProblem]:
        """Derive the rail and current step from the log."""
        return self._read(lambda cur, rp: cur.wizard.state(rp))

    def complete(self, step: str) -> Result[Committed, ApiProblem]:
        """Mark the current step done."""
        return self._act(lambda cur, rp: cur.wizard.complete(rp, StepId(step)))

    def skip(self, step: str) -> Result[Committed, ApiProblem]:
        """Explicitly skip the current step."""
        return self._act(lambda cur, rp: cur.wizard.skip(rp, StepId(step)))

    def revert(self, step: str | None) -> Result[Committed, ApiProblem]:
        """Reopen the most recently finished step."""
        return self._act(lambda cur, rp: cur.wizard.revert(rp, None if step is None else StepId(step)))

    # ---- points -----------------------------------------------------------------------

    def points(self) -> Result[list[PointView], ApiProblem]:
        """List captured points with edits applied (excluded points included, flagged)."""
        return self._read(lambda _cur, rp: [PointView.of(p) for p in rp.view().points])

    def capture(self, body: CaptureBody) -> Result[Committed, ApiProblem]:
        """Validate typed inputs, then append a POINT through the wizard."""
        parsed = parse_inputs(body.phase, body.inputs)
        if parsed.is_err:
            return Err(
                ApiProblem(
                    type="urn:sadi:error:input:missing",
                    title="missing",
                    status=422,
                    detail=parsed.danger_err,
                    hint="Fill in the required field before continuing.",
                )
            )
        meta = PointMeta(
            t_since_load_s=body.t_since_load_s,
            drift_rate=body.drift_rate,
            settled=body.settled,
            forced_early=body.forced_early,
        )
        point = build_point(parsed.danger_ok, body.window, meta)
        return self._act(lambda cur, rp: cur.wizard.capture(rp, point))

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
        return Ok(self._info(self._open))

    def _replay(self, cur: _Open) -> Result[ReplayState, ApiProblem]:
        """Recover the current ReplayState from disk."""
        got = recover_state(cur.handle.path)
        if got.is_err:
            return Err(from_model(got.danger_err, "store"))
        return Ok(got.danger_ok)

    def _read(self, fn: Callable[[_Open, ReplayState], _T]) -> Result[_T, ApiProblem]:
        """Run a read-only projection over the replayed state."""
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            rp = self._replay(cur)
            if rp.is_err:
                return Err(rp.danger_err)
            return Ok(fn(cur, rp.danger_ok))

    def _act(
        self, fn: Callable[[_Open, ReplayState], Result[Command, WizardError]]
    ) -> Result[Committed, ApiProblem]:
        """Run a wizard command, append its records, wait for durability, return the new state."""
        with self._lock:
            cur = self._open
            if cur is None:
                return Err(self._none_open())
            rp = self._replay(cur)
            if rp.is_err:
                return Err(rp.danger_err)
            cmd = fn(cur, rp.danger_ok)
            if cmd.is_err:
                return Err(from_wizard(cmd.danger_err))
            seq = 0
            for rec in cmd.danger_ok.records:
                sub = cur.writer.submit(rec)
                if sub.is_err:
                    return Err(from_model(sub.danger_err, "store"))
                seq = sub.danger_ok
            durable = cur.writer.wait_durable(seq, DURABLE_TIMEOUT_S)
            if durable.is_err:
                return Err(from_model(durable.danger_err, "store"))
            after = self._replay(cur)
            if after.is_err:
                return Err(after.danger_err)
            _log.info("committed seq %d: %s", seq, cmd.danger_ok.summary)
            return Ok(
                Committed(
                    seq=seq,
                    summary=cmd.danger_ok.summary,
                    wizard=cur.wizard.state(after.danger_ok),
                    history=cur.wizard.history(after.danger_ok),
                )
            )


