"""IncrementalReplay.notes equals a full WAL note scan (random sequences, restart, torn tail)."""

# frob:ticket 01M6X465ZVYG4B9Y79QAZ8KDXT
from __future__ import annotations

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from sadi.store.incremental import IncrementalReplay
from sadi.store.records import NewRecord, RecordType, encode_raw_block
from sadi.store.session import SessionMeta, create_session
from sadi.store.wal import WalConfig, WalReader, WalWriter

NOW = datetime(2026, 11, 8, 15, 30, 0, tzinfo=UTC)


def _full_notes(path: Path) -> list[str]:
    """Reference: the pre-incremental notes() scan."""
    return [
        r.danger_ok.payload.decode()
        for r in WalReader(path / "wal").records()
        if r.danger_ok.type == int(RecordType.NOTE) and r.danger_ok.flags & 1
    ]


def _rec(n: int, kind: str) -> NewRecord:
    """Record `n` of kind raw / json note / non-json note."""
    if kind == "raw":
        return NewRecord(
            type=int(RecordType.RAW_BLOCK), payload=encode_raw_block(b"\x01" * 64, 8, 1, 2, 0)
        )
    if kind == "note":
        return NewRecord(type=int(RecordType.NOTE), payload=f'{{"n":{n}}}'.encode(), flags=1)
    return NewRecord(type=int(RecordType.NOTE), payload=b"plain", flags=0)


def _open(root: Path, seg: int) -> tuple[Path, WalWriter]:
    """Session plus a small-segment writer."""
    h = create_session(root, SessionMeta(slug="nn"), NOW).danger_ok
    cfg = WalConfig(segment_max_bytes=seg)
    return h.path, WalWriter.open(
        h.path / "wal", uuid.UUID(h.manifest.session_uuid), 1, cfg
    ).danger_ok


# frob:tests python/sadi/store/incremental.py::IncrementalReplay.notes
@settings(max_examples=40, deadline=None)
@given(
    steps=st.lists(
        st.tuples(st.sampled_from(["raw", "raw", "note", "plain"]), st.integers(0, 3)), max_size=60
    ),
    seg=st.sampled_from([600, 2000, 1 << 20]),
)
def test_notes_equal_full_scan(steps: list[tuple[str, int]], seg: int) -> None:
    """Interleaved polling, rotation and restart never diverge from a full scan."""
    with tempfile.TemporaryDirectory() as td:
        path, w = _open(Path(td), seg)
        inc = IncrementalReplay(path)
        for n, (kind, polls) in enumerate(steps, 1):
            assert w.append(_rec(n, kind)).is_ok
            if polls:
                assert list(inc.notes().danger_ok) == _full_notes(path)
        w.close().expect("close")
        full = _full_notes(path)
        assert list(inc.notes().danger_ok) == full
        assert list(IncrementalReplay(path).notes().danger_ok) == full


# frob:tests python/sadi/store/incremental.py::IncrementalReplay.notes
def test_notes_torn_tail(tmp_path: Path) -> None:
    """A torn tail never adds or drops notes."""
    path, w = _open(tmp_path, 1 << 20)
    for i in range(1, 6):
        w.append(_rec(i, "note")).expect("append")
    w.close().expect("close")
    inc = IncrementalReplay(path)
    good = list(inc.notes().danger_ok)
    seg = next((path / "wal").glob("seg-*.wal"))
    with seg.open("ab") as f:
        f.write(b"SADIFRAM\x01\x05")
    assert list(inc.notes().danger_ok) == good == _full_notes(path)
    assert list(IncrementalReplay(path).notes().danger_ok) == good
