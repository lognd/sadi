"""Snapshots carry NOTE payloads so a rebase needs no whole-WAL walk; old snapshots still load."""

# frob:ticket 01M72YGM028WQQGWVSDX4GTJZ5
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from sadi.store import incremental, snapshot
from sadi.store.events import replay
from sadi.store.incremental import IncrementalReplay
from sadi.store.records import NewRecord, RecordType, encode_raw_block
from sadi.store.session import SessionMeta, create_session
from sadi.store.wal import WalReader, WalWriter

NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)


def _note(n: int) -> NewRecord:
    """A JSON NOTE record."""
    return NewRecord(type=int(RecordType.NOTE), payload=f'{{"n":{n}}}'.encode(), flags=1)


def _raw() -> NewRecord:
    """A raw block record."""
    return NewRecord(
        type=int(RecordType.RAW_BLOCK), payload=encode_raw_block(b"\x01" * 64, 8, 1, 2, 0)
    )


def _build(root: Path, total: int = 9) -> Path:
    """Session whose closed WAL holds alternating notes and raw blocks; return its dir."""
    h = create_session(root, SessionMeta(slug="sn"), NOW).danger_ok
    w = WalWriter.open(h.path / "wal", uuid.UUID(h.manifest.session_uuid), 1).danger_ok
    for i in range(total):
        assert w.append(_note(i) if i % 2 == 0 else _raw()).is_ok
    w.close().expect("close")
    h.close().expect("release session lock")
    return h.path


class _Dir:
    """Minimal session handle (write_snapshot only needs `.path`)."""

    def __init__(self, path: Path) -> None:
        """Wrap a session dir."""
        self.path = path


def _snap(path: Path, upto: int, with_notes: bool) -> None:
    """Snapshot the WAL as of seq `upto`, with or without notes."""
    recs = [r.danger_ok for r in WalReader(path / "wal").records() if r.danger_ok.seq <= upto]
    st = replay(recs, None, ()).danger_ok
    notes = [_text(r) for r in recs if _is_note(r)] if with_notes else None
    got = snapshot.write_snapshot(_Dir(path), st, st.covers_seq, notes=notes)
    assert got.is_ok, got


def _text(r: object) -> str:
    """Note payload text."""
    return r.payload.decode()  # type: ignore[attr-defined]


def _is_note(r: object) -> bool:
    """True for a JSON NOTE."""
    return r.type == int(RecordType.NOTE) and bool(r.flags & 1)  # type: ignore[attr-defined]


def _full(path: Path) -> list[str]:
    """Reference whole-WAL note scan."""
    return [
        r.danger_ok.payload.decode()
        for r in WalReader(path / "wal").records()
        if r.danger_ok.type == int(RecordType.NOTE) and r.danger_ok.flags & 1
    ]


# frob:tests python/sadi/store/incremental.py::IncrementalReplay._scan_notes
def test_rebase_from_snapshot_with_notes_skips_wal_walk(tmp_path: Path) -> None:
    """With stored notes the rebase reads only the tail, and notes equal a full scan."""
    path = _build(tmp_path)
    _snap(path, 6, True)
    real = incremental.WalReader
    calls: list[int | None] = []

    class Spy(real):  # type: ignore[valid-type, misc]
        """Record each records() walk's start seq."""

        def records(self, from_seq=None):  # type: ignore[no-untyped-def]
            """Delegate, noting from_seq."""
            calls.append(from_seq)
            return super().records(from_seq=from_seq) if from_seq else super().records()

    with mock.patch.object(incremental, "WalReader", Spy):
        got = IncrementalReplay(path).notes().unwrap()
    assert list(got) == _full(path)
    assert calls and all(c is not None and c > 1 for c in calls), calls


# frob:tests python/sadi/store/incremental.py::IncrementalReplay._scan_notes
def test_old_snapshot_without_notes_still_correct(tmp_path: Path) -> None:
    """A snapshot lacking notes (pre-change) falls back to the whole-WAL walk."""
    path = _build(tmp_path)
    _snap(path, 6, False)
    assert list(IncrementalReplay(path).notes().unwrap()) == _full(path)
    loaded = snapshot.load_latest_snapshot(path).danger_ok
    assert loaded is not None and loaded.notes is None


# frob:tests python/sadi/store/snapshot.py::write_snapshot
def test_snapshot_roundtrips_notes(tmp_path: Path) -> None:
    """Stored notes come back from load_latest_snapshot unchanged."""
    path = _build(tmp_path)
    _snap(path, 6, True)
    loaded = snapshot.load_latest_snapshot(path).danger_ok
    assert loaded is not None and loaded.notes == _full_prefix(path, 6)


def _full_prefix(path: Path, upto: int) -> list[str]:
    """Reference notes with seq <= upto."""
    return [
        _text(r.danger_ok)
        for r in WalReader(path / "wal").records()
        if r.danger_ok.seq <= upto and _is_note(r.danger_ok)
    ]
