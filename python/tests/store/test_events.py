"""Tests for the event log replay and atomic snapshots: determinism, history, crash safety."""

# frob:ticket 01M6W7R2F3KJWQCWEKZK6BT3MG
from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sadi.store import failpoints, snapshot
from sadi.store.events import (
    EditV1,
    EventsGap,
    EventsWal,
    PointV1,
    PointWindow,
    ReplayState,
    edit_record,
    marker_record,
    point_record,
    recover_state,
    replay,
    replay_wal,
    settings_record,
)
from sadi.store.records import (
    FLAG_JSON,
    MarkerV1,
    NewRecord,
    Record,
    RecordType,
    SettingsV1,
)
from sadi.store.session import SessionHandle, SessionMeta, create_session
from sadi.store.snapshot import SnapshotAhead, SnapshotIo, load_latest_snapshot, write_snapshot
from sadi.store.wal import WalConfig, WalReader, WalWriter

NOW = datetime(2026, 11, 8, 15, 30, 0, tzinfo=UTC)
WIN = PointWindow(first_raw_seq=2, last_raw_seq=9)


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    """Clear failpoints around each test."""
    failpoints.clear()
    yield
    failpoints.clear()


def pt(i: int) -> PointV1:
    """A deterministic point with id p<i>."""
    return PointV1(point_id=f"p{i}", phase="load", window=WIN, inputs={"load_N": 10.0 * i})


def ed(
    eid: str,
    target: str,
    op: str,
    supersedes: str | None = None,
    args: dict[str, object] | None = None,
) -> EditV1:
    """A deterministic edit."""
    return EditV1.model_validate(
        {"target": target, "op": op, "args": args or {}, "edit_id": eid, "supersedes": supersedes}
    )


def as_records(items: list[NewRecord]) -> list[Record]:
    """Number NewRecords from seq 1 as in-memory verified Records."""
    return [
        Record(type=n.type, seq=i, wall_ns=0, flags=n.flags, payload=n.payload, crc=0)
        for i, n in enumerate(items, start=1)
    ]


def make_session(
    tmp_path: Path, items: list[NewRecord], cfg: WalConfig | None = None
) -> SessionHandle:
    """Create a session and append `items` durably to its WAL (optionally with a small `cfg`)."""
    h = create_session(tmp_path, SessionMeta(slug="ev"), NOW).danger_ok
    w = WalWriter.open(h.path / "wal", uuid.UUID(h.manifest.session_uuid), 1, cfg or WalConfig())
    w.expect("open wal")
    for n in items:
        w.danger_ok.append(n).expect("append")
    w.danger_ok.close().expect("close")
    return h


def tree_hash(root: Path) -> str:
    """Hash every path and content under root."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(f"{p.relative_to(root)}|{p.is_dir()}\n".encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


BASIC = [
    settings_record(SettingsV1(scope="acquisition", key="rate", value=100)),
    point_record(pt(1)),
    point_record(pt(2)),
    marker_record(MarkerV1(kind="bookmark", label="a")),
    edit_record(ed("e1", "p1", "exclude")),
    edit_record(ed("e2", "p2", "override_input", args={"load_N": 99.0})),
    edit_record(ed("e3", "analysis", "set_fit_window", args={"first": 1, "last": 2})),
    settings_record(SettingsV1(scope="acquisition", key="rate", value=200, previous=100)),
]


# frob:tests python/sadi/store/events.py::replay
def test_current_state_is_replay_with_full_history() -> None:
    """Points, edits, settings and markers are records; state is their fold; history is kept."""
    state = replay(as_records(BASIC)).danger_ok
    v = state.view()
    assert [p.point.point_id for p in v.points] == ["p1", "p2"]
    assert v.points[0].excluded and not v.points[1].excluded
    assert v.points[1].inputs["load_N"] == 99.0 and v.points[1].point.inputs["load_N"] == 20.0
    assert v.analysis == {"fit_window": {"first": 1, "last": 2}}
    assert v.settings == {"acquisition/rate": 200}
    assert len(state.settings_log) == 2 and len(state.edits) == 3 and len(state.markers) == 1
    assert not v.anomalies and not state.skipped
    assert state.covers_seq == len(BASIC)


# frob:tests python/sadi/store/events.py::replay
def test_undo_redo_and_include_are_appended_edits() -> None:
    """Undo/redo/include never remove history; they change which edits are active."""
    items = [
        *BASIC[:3],
        edit_record(ed("e1", "p1", "exclude")),
        edit_record(ed("u1", "p1", "undo", supersedes="e1")),
    ]
    s1 = replay(as_records(items)).danger_ok
    assert not s1.view().points[0].excluded and len(s1.edits) == 2
    items.append(edit_record(ed("r1", "p1", "redo", supersedes="u1")))
    s2 = replay(as_records(items)).danger_ok
    assert s2.view().points[0].excluded and len(s2.edits) == 3
    items.append(edit_record(ed("i1", "p1", "include")))
    assert not replay(as_records(items)).danger_ok.view().points[0].excluded


# frob:tests python/sadi/store/events.py::replay
def test_odd_content_is_reported_not_fatal() -> None:
    """Unknown targets, bad undo, bad payloads and unknown types are listed, replay goes on."""
    recs = as_records(
        [
            point_record(pt(1)),
            edit_record(ed("e1", "ghost", "exclude")),
            edit_record(ed("u1", "p1", "undo", supersedes="nope")),
            NewRecord(type=int(RecordType.POINT), payload=b"{not json", flags=FLAG_JSON),
            NewRecord(type=0x55, payload=b"?"),
            point_record(pt(1)),
        ]
    )
    state = replay(recs).danger_ok
    assert len(state.view().anomalies) == 3
    assert [s.seq for s in state.skipped] == [4, 5]
    assert len(state.view().points) == 1


# frob:tests python/sadi/store/events.py::replay
def test_gap_after_base_is_an_error() -> None:
    """A record that does not continue the base state is an Err, not silently accepted."""
    recs = as_records(BASIC)
    base = replay(recs[:3]).danger_ok
    res = replay([recs[4]], base)
    assert res.is_err and isinstance(res.danger_err, EventsGap)


# frob:tests python/sadi/store/events.py::replay_wal
def test_replay_from_wal_never_modifies_it(tmp_path: Path) -> None:
    """Replaying a real WAL leaves the session tree byte-identical."""
    h = make_session(tmp_path, BASIC)
    before = tree_hash(h.path)
    state = replay_wal(h.path / "wal").danger_ok
    assert state == replay(as_records(BASIC)).danger_ok.model_copy(
        update={"covers_seq": state.covers_seq}
    )
    assert tree_hash(h.path) == before


# frob:tests python/sadi/store/events.py::replay_wal
def test_corrupt_wal_is_err_and_untouched(tmp_path: Path) -> None:
    """Mid-log corruption stops replay with Err(EventsWal) and changes no bytes."""
    h = make_session(tmp_path, BASIC)
    seg = next((h.path / "wal").glob("seg-*.wal"))
    data = bytearray(seg.read_bytes())
    data[100] ^= 0xFF
    seg.write_bytes(bytes(data))
    before = tree_hash(h.path)
    res = replay_wal(h.path / "wal")
    assert res.is_err and isinstance(res.danger_err, EventsWal)
    assert tree_hash(h.path) == before


# frob:tests python/sadi/store/snapshot.py::write_snapshot
def test_snapshot_roundtrip_and_recovery_matches_full_replay(tmp_path: Path) -> None:
    """Snapshot at k plus WAL tail equals a full replay, and the snapshot is really used."""
    h = make_session(tmp_path, BASIC)
    full = replay_wal(h.path / "wal").danger_ok
    mid = replay(as_records(BASIC)[:5]).danger_ok
    path = write_snapshot(h, mid, 5, now=NOW).danger_ok
    assert path.parent == h.path / "snapshots" and path.name.startswith("snap-000000000005-")
    snap = load_latest_snapshot(h.path).danger_ok
    assert snap is not None and snap.covers_seq == 5
    assert recover_state(h.path).danger_ok == full
    assert not list((h.path / "snapshots").glob(".*tmp"))


# frob:tests python/sadi/store/snapshot.py::load_latest_snapshot
def test_corrupt_stale_and_ahead_snapshots_are_ignored_not_deleted(tmp_path: Path) -> None:
    """Bit-flipped, wrong-hash, future and tmp snapshots are skipped; replay still recovers."""
    h = make_session(tmp_path, BASIC)
    full = replay_wal(h.path / "wal").danger_ok
    recs = as_records(BASIC)
    good = write_snapshot(h, replay(recs[:3]).danger_ok, 3, now=NOW).danger_ok
    bad = write_snapshot(h, replay(recs[:6]).danger_ok, 6, now=NOW).danger_ok
    raw = bytearray(bad.read_bytes())
    raw[-3] ^= 0x01
    bad.write_bytes(bytes(raw))
    stale = write_snapshot(
        h, replay(recs[:7]).danger_ok, 7, prefix_hash_hex="00" * 32, now=NOW
    ).danger_ok
    ahead = write_snapshot(
        h, replay(recs).danger_ok, 99, prefix_hash_hex="11" * 32, now=NOW
    ).danger_ok
    leftover = h.path / "snapshots" / ".snap-8-1-dead.tmp"
    leftover.write_bytes(b"half a frame")
    snap = load_latest_snapshot(h.path).danger_ok
    assert snap is not None and snap.covers_seq == 3
    assert recover_state(h.path).danger_ok == full
    for p in (good, bad, stale, ahead, leftover):
        assert p.exists()


# frob:tests python/sadi/store/snapshot.py::load_latest_snapshot
def test_all_snapshots_bad_replays_from_wal(tmp_path: Path) -> None:
    """With no usable snapshot recovery is a full replay."""
    h = make_session(tmp_path, BASIC)
    p = write_snapshot(h, ReplayState(), 4, prefix_hash_hex="22" * 32, now=NOW).danger_ok
    assert load_latest_snapshot(h.path).danger_ok is None
    assert recover_state(h.path).danger_ok == replay_wal(h.path / "wal").danger_ok
    assert p.exists()


# frob:tests python/sadi/store/events.py::recover_state
def test_snapshot_with_unusable_state_falls_back_to_full_replay(tmp_path: Path) -> None:
    """A CRC- and hash-valid snapshot whose state does not parse does not block recovery."""
    h = make_session(tmp_path, BASIC)
    ph = snapshot.prefix_hash(h.path / "wal", 4).danger_ok

    class Junk(ReplayState):
        """Wrong-shaped state."""

        covers_seq: int = 4

    class Weird(snapshot.BaseModel):
        """State that is not a ReplayState."""

        points: str = "nope"

    write_snapshot(h, Weird(), 4, prefix_hash_hex=ph, now=NOW)
    assert recover_state(h.path).danger_ok == replay_wal(h.path / "wal").danger_ok


# frob:tests python/sadi/store/snapshot.py::write_snapshot
@pytest.mark.parametrize(
    ("point", "published"),
    [
        ("durable.rename", False),
        ("snapshot.write", False),
        ("snapshot.fsync", False),
        ("snapshot.rename", False),
        ("snapshot.dirsync", True),
    ],
)
def test_failure_at_each_step_never_leaves_a_bad_final_file(
    tmp_path: Path, point: str, published: bool
) -> None:
    """A failure before the rename leaves no final name; after it the file is complete."""
    h = make_session(tmp_path, BASIC)
    full = replay_wal(h.path / "wal").danger_ok
    failpoints.configure({point: "error:5"})
    res = write_snapshot(h, full, full.covers_seq, now=NOW)
    failpoints.clear()
    assert res.is_err and isinstance(res.danger_err, SnapshotIo)
    finals = list((h.path / "snapshots").glob("snap-*.snap"))
    assert bool(finals) is published
    for f in finals:
        assert snapshot._parse_snapshot(f) is not None
    assert recover_state(h.path).danger_ok == full


# frob:tests python/sadi/store/snapshot.py::write_snapshot
def test_never_overwrites_an_existing_snapshot(tmp_path: Path) -> None:
    """Two snapshots with the same covers_seq and timestamp get distinct names."""
    h = make_session(tmp_path, BASIC)
    st1 = replay_wal(h.path / "wal").danger_ok
    a = write_snapshot(h, st1, st1.covers_seq, now=NOW).danger_ok
    before = a.read_bytes()
    b = write_snapshot(h, st1, st1.covers_seq, now=NOW).danger_ok
    assert a != b and a.read_bytes() == before and b.exists()


# frob:tests python/sadi/store/snapshot.py::write_snapshot
def test_ahead_of_wal_is_refused_and_ref_is_best_effort(tmp_path: Path) -> None:
    """covers_seq beyond the log is Err(SnapshotAhead); SNAPSHOT_REF failure does not fail."""
    h = make_session(tmp_path, BASIC)
    st1 = replay_wal(h.path / "wal").danger_ok
    res = write_snapshot(h, st1, 50, now=NOW)
    assert res.is_err and isinstance(res.danger_err, SnapshotAhead)
    assert not list((h.path / "snapshots").iterdir())
    seen: list[NewRecord] = []

    def sink(rec: NewRecord):  # noqa: ANN202
        seen.append(rec)
        raise OSError(5, "boom")

    assert write_snapshot(h, st1, st1.covers_seq, ref_sink=sink, now=NOW).is_ok
    assert len(seen) == 1 and seen[0].type == int(RecordType.SNAPSHOT_REF)


# ---- property: determinism -----------------------------------------------------------------

_ids = st.sampled_from(["p1", "p2", "p3", "ghost", "analysis"])
_ops = st.sampled_from(["exclude", "include", "set_window", "override_input", "set_fit_window"])


@st.composite
def _logs(draw: st.DrawFn) -> list[NewRecord]:
    """A random event log with edits, undo/redo and settings."""
    n = draw(st.integers(1, 30))
    out: list[NewRecord] = [point_record(pt(i)) for i in (1, 2, 3)]
    eids: list[str] = []
    for i in range(n):
        kind = draw(st.sampled_from(["edit", "undo", "redo", "setting", "marker", "point"]))
        if kind == "edit":
            eid = f"e{i}"
            eids.append(eid)
            op = draw(_ops)
            extra: dict[str, object] = (
                {"last_raw_seq": draw(st.integers(0, 20))} if op == "set_window" else {"k": i}
            )
            out.append(edit_record(ed(eid, draw(_ids), op, args=extra)))
        elif kind in ("undo", "redo") and eids:
            out.append(edit_record(ed(f"x{i}", "p1", kind, supersedes=draw(st.sampled_from(eids)))))
        elif kind == "setting":
            out.append(settings_record(SettingsV1(scope="s", key=draw(_ids), value=i)))
        elif kind == "marker":
            out.append(marker_record(MarkerV1(kind="m", label=str(i))))
        else:
            out.append(point_record(pt(draw(st.integers(1, 5)))))
    return out


# frob:tests python/sadi/store/events.py::replay
@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(items=_logs(), cut=st.integers(0, 40))
def test_replay_is_deterministic_and_snapshot_resumable(items: list[NewRecord], cut: int) -> None:
    """Same log -> identical state; snapshot-style resume at any cut equals a full replay."""
    recs = as_records(items)
    a = replay(recs).danger_ok
    b = replay(list(recs)).danger_ok
    assert a == b and a.view() == b.view()
    assert a.model_dump_json() == b.model_dump_json()
    k = min(cut, len(recs))
    head = replay(recs[:k]).danger_ok
    restored = ReplayState.model_validate_json(head.model_dump_json())
    assert replay(recs, restored).danger_ok == a
    assert replay(recs[k:], restored).danger_ok == a if k else True


# ---- rotated WALs (SEAL records consume a seq but are not data records) -----------------

ROTATING = WalConfig(segment_max_bytes=600)


def rotated_session(tmp_path: Path) -> SessionHandle:
    """A session whose WAL spans several segments (and so several seals)."""
    items = [point_record(pt(i)) for i in range(1, 25)]
    h = make_session(tmp_path, items, ROTATING)
    assert len(list((h.path / "wal").glob("seg-*.wal"))) >= 3
    return h


# frob:ticket 01M6WJMCTQ6M9SW2C3W6H5B4R2
# frob:tests python/sadi/store/events.py::replay_wal
def test_replay_wal_across_rotations(tmp_path: Path) -> None:
    """A multi-segment WAL replays completely; seals are skipped but never lose a record."""
    h = rotated_session(tmp_path)
    state = replay_wal(h.path / "wal").danger_ok
    assert [p.point.point_id for p in state.points] == [f"p{i}" for i in range(1, 25)]
    assert state.record_count == 24
    assert state.covers_seq > 24  # seals consumed seqs


# frob:ticket 01M6WJMCTQ6M9SW2C3W6H5B4R2
# frob:tests python/sadi/store/events.py::recover_state
def test_snapshot_assisted_recovery_across_a_seal(tmp_path: Path) -> None:
    """A snapshot taken just before a seal plus the tail equals a full replay."""
    h = rotated_session(tmp_path)
    scan = WalReader.scan(h.path / "wal").danger_ok
    assert scan.seal_seqs
    full = replay_wal(h.path / "wal").danger_ok
    for seal in scan.seal_seqs[:2]:
        cover = seal - 1  # last data seq before this seal
        recs = [r.danger_ok for r in WalReader(h.path / "wal").records() if r.is_ok]
        base = replay([r for r in recs if r.seq <= cover], None, scan.seal_seqs).danger_ok
        assert base.covers_seq == cover
        write_snapshot(h, base, cover, now=NOW).expect("snapshot")
        assert recover_state(h.path).danger_ok == full


# frob:ticket 01M6WJMCTQ6M9SW2C3W6H5B4R2
# frob:tests python/sadi/store/events.py::replay
def test_only_seal_seqs_are_tolerated_as_jumps() -> None:
    """A jump over a declared seal seq is fine; any other gap is still EventsGap."""
    recs = as_records(BASIC)
    skipped_seal = [r.model_copy(update={"seq": r.seq + (1 if r.seq > 3 else 0)}) for r in recs]
    ok = replay(skipped_seal, None, seal_seqs={4})
    assert ok.is_ok and ok.danger_ok.record_count == len(BASIC)
    undeclared = replay(skipped_seal)
    assert undeclared.is_err and undeclared.danger_err == EventsGap(expected=4, found=5)
    wrong = replay(skipped_seal, None, seal_seqs={7})
    assert wrong.is_err and isinstance(wrong.danger_err, EventsGap)
    # a genuine gap next to a real seal is still detected
    dropped = [r for r in skipped_seal if r.seq != 6]
    res = replay(dropped, None, seal_seqs={4})
    assert res.is_err and res.danger_err == EventsGap(expected=6, found=7)
