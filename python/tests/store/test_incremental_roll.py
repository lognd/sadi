"""A WAL segment roll must not force an IncrementalReplay rebase (audit8 H1)."""

# frob:ticket 01M72Y6ZT01R2CXQT2XM4CMVZT
from __future__ import annotations

from pathlib import Path

import pytest

from sadi.store import snapshot
from sadi.store.events import PointV1, PointWindow, point_record, recover_state
from sadi.store.incremental import IncrementalReplay
from sadi.store.records import NewRecord, RecordType, encode_raw_block
from tests.store.test_incremental import _open

WIN = PointWindow(first_raw_seq=1, last_raw_seq=2)


def _raw() -> NewRecord:
    """A RAW_BLOCK record that consumes a seq."""
    return NewRecord(
        type=int(RecordType.RAW_BLOCK), payload=encode_raw_block(b"\x01" * 64, 8, 1, 2, 0)
    )


# frob:tests python/sadi/store/incremental.py::IncrementalReplay.state
def test_roll_does_not_rebase_and_equals_full_replay(tmp_path: Path) -> None:
    """Appending across several segment rolls keeps `rebases` at 1 and state == full replay."""
    path, w = _open(tmp_path, 600)
    inc = IncrementalReplay(path)
    for _ in range(3):
        w.append(_raw()).expect("append")
    assert inc.state().is_ok
    assert inc.rebases == 1
    for i in range(4, 80):
        rec = point_record(PointV1(point_id=f"p{i}", phase="load", window=WIN, inputs={"x": i}))
        w.append(rec if i % 5 == 0 else _raw()).expect("append")
        assert inc.state().danger_ok == recover_state(path).danger_ok
    w.close().expect("close")
    assert len(list((path / "wal").glob("seg-*.wal"))) > 2
    assert inc.state().danger_ok == recover_state(path).danger_ok
    assert inc.rebases == 1


# frob:tests python/sadi/store/snapshot.py::prefix_hashes_at
def test_prefix_hashes_stop_at_max_covers(tmp_path: Path) -> None:
    """The scan stops at the largest wanted seq, yet hashes equal a full-walk hash."""
    path, w = _open(tmp_path, 1 << 20)
    for _ in range(10):
        w.append(_raw()).expect("append")
    w.close().expect("close")
    hashes, last = snapshot.prefix_hashes_at(path / "wal", [3, 5]).danger_ok
    assert last == 5
    full, full_last = snapshot.prefix_hashes_at(path / "wal", [3, 5, 10]).danger_ok
    assert full_last == 10
    assert hashes == {3: full[3], 5: full[5]}


# frob:tests python/sadi/store/incremental.py::IncrementalReplay.prefix_hash_at
def test_snapshot_rebase_keeps_running_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a snapshot-based rebase and a roll, the running hash is exact; no prefix_hash walk."""
    path, w = _open(tmp_path, 600)
    for _ in range(6):
        w.append(_raw()).expect("append")
    first = IncrementalReplay(path)
    state = first.state().danger_ok

    class _H:
        """Minimal session handle exposing the directory."""

        def __init__(self, p: Path) -> None:
            self.path = p

    snapshot.write_snapshot(
        _H(path), state, state.covers_seq, prefix_hash_hex=first.prefix_hash_at(state.covers_seq)
    ).expect("snapshot")
    inc = IncrementalReplay(path)
    assert inc.state().is_ok
    for _ in range(30):
        w.append(_raw()).expect("append")
    final = inc.state().danger_ok
    assert inc.rebases == 1
    w.close().expect("close")
    monkeypatch.setattr(snapshot, "prefix_hash", lambda *a, **k: pytest.fail("full walk"))
    want = snapshot.prefix_hashes_at(path / "wal", [final.covers_seq]).danger_ok[0]
    assert inc.prefix_hash_at(final.covers_seq) == want[final.covers_seq]
