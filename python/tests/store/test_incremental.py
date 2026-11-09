"""IncrementalReplay equals a full replay on random event sequences (data-safety mandate)."""

# frob:ticket 01M6X3AVGVT23M1E9V82RWJ137
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sadi.store.events import (
    EditV1,
    PointV1,
    PointWindow,
    edit_record,
    marker_record,
    point_record,
    recover_state,
    settings_record,
)
from sadi.store.incremental import IncrementalReplay
from sadi.store.records import MarkerV1, NewRecord, RecordType, SettingsV1, encode_raw_block
from sadi.store.session import SessionMeta, create_session
from sadi.store.wal import WalConfig, WalWriter

NOW = datetime(2026, 11, 8, 15, 30, 0, tzinfo=UTC)
WIN = PointWindow(first_raw_seq=1, last_raw_seq=2)


def _raw() -> NewRecord:
    """A RAW_BLOCK record (binary payload, ignored by the fold but consuming a seq)."""
    return NewRecord(
        type=int(RecordType.RAW_BLOCK), payload=encode_raw_block(b"\x01" * 64, 8, 1, 2, 0)
    )


def _make(n: int, kind: str) -> NewRecord:
    """Build record `n` of the given kind (ids derive from n; undo/redo hit real ids)."""
    if kind == "raw":
        return _raw()
    if kind == "point":
        return point_record(PointV1(point_id=f"p{n}", phase="load", window=WIN, inputs={"x": n}))
    if kind == "marker":
        return marker_record(MarkerV1(kind="bookmark", label=str(n)))
    if kind == "setting":
        return settings_record(SettingsV1(scope="a", key="k", value=n))
    if kind == "note":
        return NewRecord(type=int(RecordType.NOTE), payload=b"{}", flags=1)
    op = {"exclude": "exclude", "undo": "undo", "redo": "redo"}[kind]
    target = f"e{max(n - 1, 0)}"
    return edit_record(
        EditV1.model_validate(
            {
                "target": f"p{max(n - 3, 1)}",
                "op": op,
                "args": {},
                "edit_id": f"e{n}",
                "supersedes": target if op != "exclude" else None,
            }
        )
    )


KINDS = ["raw", "raw", "raw", "point", "marker", "setting", "note", "exclude", "undo", "redo"]
STEP = st.tuples(st.sampled_from(KINDS), st.integers(0, 3))


def _open(tmp_path: Path, seg_bytes: int) -> tuple[Path, WalWriter]:
    """Create a session and a WAL writer with small segments to force rotation."""
    h = create_session(tmp_path, SessionMeta(slug="inc"), NOW).danger_ok
    cfg = WalConfig(segment_max_bytes=seg_bytes)
    w = WalWriter.open(h.path / "wal", uuid.UUID(h.manifest.session_uuid), 1, cfg).danger_ok
    h.close().expect("release session lock")  # Windows cannot delete an open lock file
    return h.path, w


# frob:tests python/sadi/store/incremental.py::IncrementalReplay.state
@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(steps=st.lists(STEP, min_size=0, max_size=60), seg=st.sampled_from([600, 2000, 1 << 20]))
# frob:tests python/sadi/store/incremental.py::IncrementalReplay.__init__
def test_incremental_equals_full_replay(steps: list[tuple[str, int]], seg: int) -> None:
    """After every random batch (with rotation) the cache equals recover_state."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path, w = _open(Path(td), seg)
        inc = IncrementalReplay(path)
        n = 0
        for kind, polls in steps:
            n += 1
            assert w.append(_make(n, kind)).is_ok
            if polls:
                assert inc.state().danger_ok == recover_state(path).danger_ok
        assert inc.state().danger_ok == recover_state(path).danger_ok
        w.close().expect("close")
        full = recover_state(path).danger_ok
        assert inc.state().danger_ok == full
        # restart: a fresh cache over the finished WAL equals the old one
        assert IncrementalReplay(path).state().danger_ok == full


# frob:tests python/sadi/store/incremental.py::IncrementalReplay.state
def test_torn_tail_then_restart_matches_full_replay(tmp_path: Path) -> None:
    """A torn tail is ignored identically by the cache, before and after more tail bytes."""
    path, w = _open(tmp_path, 1 << 20)
    for i in range(1, 8):
        w.append(_make(i, "point" if i % 2 else "raw")).expect("append")
    w.close().expect("close")
    inc = IncrementalReplay(path)
    seg = next((path / "wal").glob("seg-*.wal"))
    good = inc.state().danger_ok
    with seg.open("ab") as f:
        f.write(b"SADIFRAM\x01\x05")  # partial frame header
    assert inc.state().danger_ok == recover_state(path).danger_ok == good
    assert IncrementalReplay(path).state().danger_ok == good


# frob:tests python/sadi/store/incremental.py::IncrementalReplay.state
def test_corruption_is_reported_not_cached(tmp_path: Path) -> None:
    """Mid-log corruption surfaces as Err from the cache exactly as from a full replay."""
    path, w = _open(tmp_path, 1 << 20)
    for i in range(1, 6):
        w.append(_make(i, "point")).expect("append")
    inc = IncrementalReplay(path)
    assert inc.state().is_ok
    w.close().expect("close")
    seg = next((path / "wal").glob("seg-*.wal"))
    data = bytearray(seg.read_bytes())
    data[100] ^= 0xFF
    seg.write_bytes(bytes(data))
    assert recover_state(path).is_err
    assert IncrementalReplay(path).state().is_err


# frob:tests python/sadi/store/incremental.py::IncrementalReplay.state
def test_steady_state_does_not_rebase(tmp_path: Path) -> None:
    """Appending within one segment never triggers a full replay after the first."""
    path, w = _open(tmp_path, 1 << 28)
    inc = IncrementalReplay(path)
    for i in range(1, 30):
        w.append(_make(i, "raw" if i % 3 else "point")).expect("append")
        assert inc.state().is_ok
    w.close().expect("close")
    assert inc.rebases == 1
    assert inc.state().danger_ok == recover_state(path).danger_ok


@pytest.mark.parametrize("kind", ["point", "raw"])
def test_empty_wal(tmp_path: Path, kind: str) -> None:
    """An empty WAL (header only) folds to the empty state."""
    path, w = _open(tmp_path, 1 << 20)
    assert IncrementalReplay(path).state().danger_ok == recover_state(path).danger_ok
    w.close().expect("close")
