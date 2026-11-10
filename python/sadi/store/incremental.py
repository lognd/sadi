"""Incremental replay: keep the folded session state and apply only newly appended WAL records.

`recover_state` walks and CRC-verifies the whole WAL, which is O(WAL) and, with a simulator
writing raw blocks continuously, grows without bound. `IncrementalReplay` does that once (and
again whenever anything is unexpected) and afterwards reads only the bytes appended past the last
applied frame. Safety rule: the fast path never guesses. A CRC failure, seq discontinuity, bad
header, trailing bytes after a SEAL or missing segment all fall back to a full verified
replay, which is the single source of truth for corruption, torn tails and gaps. The result is
therefore always equal to `recover_state` of the same bytes (property-tested). Not
thread-safe; callers lock.
"""

# frob:ticket 01M6X3AVGVT23M1E9V82RWJ137
from __future__ import annotations

from pathlib import Path
from typing import Any

from typani import Err, Ok, Result, propagate

from sadi.logging_setup import get_logger
from sadi.store import snapshot
from sadi.store.events import (
    EventsError,
    EventsWal,
    ReplayState,
    _Acc,
    _apply,
    replay,
    restore_state,
)
from sadi.store.records import (
    FLAG_JSON,
    FRAME_HEADER_LEN,
    Record,
    RecordType,
    decode_payload_check,
    new_prefix_hash,
    parse_header,
    prefix_hash_update,
)
from sadi.store.wal import (
    SEGMENT_HEADER_LEN,
    WalReader,
    decode_segment_header,
    segment_name,
)

_log = get_logger(__name__)


def _is_note(rec: Record) -> bool:
    """True for a JSON NOTE record (the only kind `notes()` returns)."""
    return rec.type == int(RecordType.NOTE) and bool(rec.flags & FLAG_JSON)


def _note_text(rec: Record) -> str:
    """Decode a NOTE payload."""
    return rec.payload.decode("utf-8")


class IncrementalReplay:
    """Cached fold of one session's WAL, advanced by tailing the active segment."""

    def __init__(self, session_dir: Path) -> None:
        """Track the WAL under `session_dir`; nothing is read until `state` is called."""
        self._wal = session_dir / "wal"
        self._session_dir = session_dir
        self._acc: _Acc | None = None
        self._frozen: ReplayState | None = None
        self._seg = 1
        self._pos = 0
        self._expected: int | None = None
        self._notes: list[str] = []
        self.rebases = 0
        # frob:ticket 01M71YY12XP2ZDM402A00A7RJW
        self._hash: Any = None
        self._hash_seq: int | None = None

    def state(self) -> Result[ReplayState, EventsError]:
        """Return the state of the verified WAL as of now (equal to a full replay)."""
        if self._acc is not None:
            before = self._acc.count
            if self._advance():
                if self._acc.count != before or self._frozen is None:
                    self._frozen = self._acc.freeze()
                return Ok(self._frozen)
        return self._rebase()

    # frob:ticket 01M71YY12XP2ZDM402A00A7RJW
    def prefix_hash_at(self, covers_seq: int) -> str | None:
        """Return the running section 9.2 prefix hash if exactly at `covers_seq`, else None."""
        if self._hash is None or self._hash_seq != covers_seq:
            return None
        return self._hash.hexdigest()

    # frob:ticket 01M6X465ZVYG4B9Y79QAZ8KDXT
    @propagate
    def notes(self) -> Result[tuple[str, ...], EventsError]:
        """Return every JSON NOTE payload in WAL order (equal to a full scan)."""
        got = self.state()
        got.unwrap()
        return Ok(tuple(self._notes))

    @propagate
    def _rebase(self) -> Result[ReplayState, EventsError]:
        """Full verified replay (snapshot + WAL); re-derive the tail position from its report."""
        self.rebases += 1
        self._acc = None
        self._frozen = None
        self._notes = []
        self._hash, self._hash_seq = None, None
        base: ReplayState | None = None
        base_hash: Any = None
        loaded = snapshot.load_latest_snapshot_hashed(self._session_dir)
        if loaded.is_err:
            _log.warning("snapshot lookup failed (%s); replaying whole WAL", loaded.danger_err)
        elif loaded.danger_ok is not None:
            base = restore_state(loaded.danger_ok[0])
            if base is not None:
                base_hash = loaded.danger_ok[1]
        reader = WalReader(self._wal)
        recs = []
        for item in reader.records(from_seq=(base.covers_seq + 1) if base else 1):
            if item.is_err:
                _log.error("replay of %s stopped by corruption: %s", self._wal, item.danger_err)
                return Err(EventsWal(error=item.danger_err))
            recs.append(item.danger_ok)
        # frob:ticket 01M72Y6ZT01R2CXQT2XM4CMVZT
        # the hash resumes from the snapshot's running state so _snapshot never rescans the WAL
        self._hash = base_hash if base is not None else new_prefix_hash()
        self._hash_seq = base.covers_seq if base is not None else None
        for rec in recs:
            if base is not None and rec.seq <= base.covers_seq:
                continue
            prefix_hash_update(self._hash, rec)
            self._hash_seq = rec.seq
        report = reader.report
        seals = report.seal_seqs if report else ()
        folded = replay(recs, base, seals)
        state = folded.unwrap()
        notes = self._scan_notes(recs, base).unwrap()
        if report is None or not report.segments:
            _log.info("no segment position for %s; incremental cache stays cold", self._wal)
            return Ok(state)
        last = report.segments[-1]
        if last.sealed:
            self._seg, self._pos = last.segment_no + 1, 0
            self._expected = (report.seal_seqs[-1] + 1) if report.seal_seqs else None
        else:
            self._seg, self._pos = last.segment_no, last.verified_bytes
            self._expected = state.covers_seq + 1 if state.covers_seq else None
        self._notes = notes
        self._acc = _Acc(state)
        self._frozen = state
        _log.info(
            "incremental replay rebased: covers_seq=%d seg=%d pos=%d",
            state.covers_seq,
            self._seg,
            self._pos,
        )
        return Ok(state)

    @propagate
    def _scan_notes(
        self, recs: list[Record], base: ReplayState | None
    ) -> Result[list[str], EventsError]:
        """Collect NOTE payloads; snapshots hold no notes, so a snapshot base needs a full walk."""
        if base is not None:
            recs = []
            for item in WalReader(self._wal).records():
                recs.append(item.map_err(lambda e: EventsWal(error=e)).unwrap())
        return Ok([_note_text(r) for r in recs if _is_note(r)])

    def _advance(self) -> bool:
        """Apply frames appended since the last call; False means 'fall back to a rebase'.

        A SEAL is the normal end of a segment: the tail moves to the next segment instead of
        rebasing. Only a gap, CRC error, bad header or trailing bytes after a SEAL rebase.
        """
        assert self._acc is not None
        while True:
            sealed = self._advance_segment()
            if sealed is None:
                return False
            if not sealed:
                return True
            self._seg += 1
            self._pos = 0

    def _advance_segment(self) -> bool | None:
        """Tail one segment: True if it ended in a SEAL, False if still live, None to rebase."""
        acc = self._acc
        assert acc is not None
        path = self._wal / segment_name(self._seg)
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            # next segment not created yet
            return False if (self._seg > 1 and self._pos == 0) else None
        with path.open("rb") as f:
            if self._pos < SEGMENT_HEADER_LEN or self._expected is None:
                if size < SEGMENT_HEADER_LEN:
                    return False if self._pos == 0 else None
                hdr = decode_segment_header(f.read(SEGMENT_HEADER_LEN), self._seg)
                if hdr.is_err or hdr.danger_ok.segment_no != self._seg:
                    return None
                first = hdr.danger_ok.first_seq
                if self._pos < SEGMENT_HEADER_LEN and self._expected not in (None, first):
                    return None
                self._expected = first if self._expected is None else self._expected
                self._pos = max(self._pos, SEGMENT_HEADER_LEN)
            f.seek(self._pos)
            while self._pos + FRAME_HEADER_LEN <= size:
                header = f.read(FRAME_HEADER_LEN)
                parsed = parse_header(header, self._pos)
                if parsed.is_err:
                    return None
                length = parsed.danger_ok[4]
                end = self._pos + FRAME_HEADER_LEN + length
                if end > size:
                    break  # frame still being written
                decoded = decode_payload_check(header, f.read(length), self._pos)
                if decoded.is_err:
                    return None
                rec = decoded.danger_ok
                if rec.seq != self._expected:
                    return None
                if rec.type == int(RecordType.SEAL):
                    # SEAL consumes a seq but is not a data record: no apply, no hash
                    self._expected = rec.seq + 1
                    self._pos = end
                    if end != size:
                        _log.warning("bytes after SEAL in %s; rebasing", path)
                        return None
                    _log.info("segment %d sealed at seq %d; tailing next", self._seg, rec.seq)
                    return True
                _apply(acc, rec)
                if self._hash is not None:
                    prefix_hash_update(self._hash, rec)
                    self._hash_seq = rec.seq
                if _is_note(rec):
                    self._notes.append(_note_text(rec))
                self._expected = rec.seq + 1
                self._pos = end
        return False
