"""Tests for emergency spill import: discovery, validation, new-version import, corrupt tail."""

# frob:ticket 01M6WEFG8X91K7313MGJQPFW6F
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sadi.store.manifest import read_manifest
from sadi.store.records import FRAME_HEADER_LEN, NewRecord, Record, RecordType, encode_frame
from sadi.store.session import SessionMeta, create_session
from sadi.store.spill import (
    SpillEmpty,
    SpillHeaderInvalid,
    discover_spills,
    import_all_spills,
    scan_spill,
    write_spill,
)
from sadi.store.wal import WalConfig, WalReader, WalWriter, encode_segment_header

NOTE = int(RecordType.NOTE)


def make_spill(path: Path, first_seq: int, n: int, session: uuid.UUID | None = None) -> bytes:
    """Write a spill file of n NOTE frames and return its bytes."""
    data = encode_segment_header(1, first_seq, session or uuid.uuid4())
    for i in range(n):
        data += encode_frame(NOTE, first_seq + i, 1000 + i, 0, bytes([i]) * 20)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return (data_root, user_dir, temp_dir) under tmp_path."""
    return tmp_path / "root", tmp_path / "user", tmp_path / "tmp"


# frob:tests python/sadi/store/spill.py::discover_spills
def test_discovers_all_three_locations(tmp_path: Path) -> None:
    """Spills in data-root, user dir and temp are found; unrelated temp files are not."""
    root, user, tmp = dirs(tmp_path)
    make_spill(root / "spill" / "a.wal", 1, 1)
    make_spill(user / "spill" / "b.wal", 1, 1)
    make_spill(tmp / "sadi-spill-c.wal", 1, 1)
    (tmp / "other.wal").write_bytes(b"x")
    found = discover_spills(root, user, tmp)
    assert [p.name for p in found] == ["a.wal", "b.wal", "sadi-spill-c.wal"]


# frob:tests python/sadi/store/spill.py::import_all_spills
def test_valid_spill_becomes_new_version_and_is_kept(tmp_path: Path) -> None:
    """A valid spill imports verbatim as a verifiable new version; the original is untouched."""
    root, user, tmp = dirs(tmp_path)
    spill = root / "spill" / "s.wal"
    data = make_spill(spill, 5, 4)
    out = import_all_spills(root, user, tmp)
    assert len(out) == 1
    rep = out[0][1].danger_ok
    assert rep is not None
    assert (rep.first_seq, rep.last_seq, rep.record_count, rep.tail) == (5, 8, 4, None)
    assert spill.read_bytes() == data
    scanned = WalReader.scan(rep.version_dir / "wal").danger_ok
    assert scanned.record_count == 4
    assert scanned.last_seq == 8


def test_second_start_does_not_reimport(tmp_path: Path) -> None:
    """A marker beside the spill prevents repeat imports; the version dir count stays 1."""
    root, user, tmp = dirs(tmp_path)
    make_spill(root / "spill" / "s.wal", 1, 2)
    assert import_all_spills(root, user, tmp)[0][1].danger_ok is not None
    assert import_all_spills(root, user, tmp)[0][1].danger_ok is None
    assert len(list((root / "sessions").iterdir())) == 1


# frob:tests python/sadi/store/spill.py::scan_spill
def test_corrupt_tail_imports_prefix_and_reports_rest(tmp_path: Path) -> None:
    """A flipped byte in frame 3 imports frames 1-2, reports the tail, never truncates."""
    root, user, tmp = dirs(tmp_path)
    spill = root / "spill" / "s.wal"
    data = bytearray(make_spill(spill, 1, 4))
    frame = FRAME_HEADER_LEN + 20
    bad_at = 64 + 2 * frame
    data[bad_at + FRAME_HEADER_LEN + 3] ^= 0xFF
    spill.write_bytes(bytes(data))
    scan = scan_spill(spill).danger_ok
    assert scan.record_count == 2
    assert scan.tail is not None
    assert (scan.tail.offset, scan.tail.length) == (bad_at, 2 * frame)
    assert scan.tail.sha256 == hashlib.sha256(bytes(data[bad_at:])).hexdigest()
    rep = import_all_spills(root, user, tmp)[0][1].danger_ok
    assert rep is not None
    assert rep.record_count == 2
    assert rep.tail == scan.tail
    assert spill.read_bytes() == bytes(data)
    assert WalReader.scan(rep.version_dir / "wal").danger_ok.last_seq == 2


def test_partial_frame_tail(tmp_path: Path) -> None:
    """A file cut mid-frame keeps the whole frames and reports the partial bytes."""
    root, _, _ = dirs(tmp_path)
    spill = root / "spill" / "s.wal"
    data = make_spill(spill, 1, 3)
    spill.write_bytes(data[:-7])
    scan = scan_spill(spill).danger_ok
    assert scan.record_count == 2
    assert scan.tail is not None
    assert scan.tail.reason == "partial payload"
    assert spill.stat().st_size == len(data) - 7


def test_seq_gap_stops_prefix(tmp_path: Path) -> None:
    """A CRC-valid frame with the wrong seq ends the verified prefix."""
    root, _, _ = dirs(tmp_path)
    spill = root / "spill" / "s.wal"
    data = make_spill(spill, 1, 2) + encode_frame(NOTE, 9, 0, 0, b"zz")
    spill.write_bytes(data)
    scan = scan_spill(spill).danger_ok
    assert scan.record_count == 2
    assert scan.tail is not None and "seq 9" in scan.tail.reason


def test_bad_header_and_empty_are_errors(tmp_path: Path) -> None:
    """Garbage and header-only spills import nothing and create no version dir."""
    root, user, tmp = dirs(tmp_path)
    bad = root / "spill" / "bad.wal"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"garbage" * 20)
    make_spill(root / "spill" / "empty.wal", 1, 0)
    out = dict(import_all_spills(root, user, tmp))
    assert isinstance(out[bad].danger_err, SpillHeaderInvalid)
    assert isinstance(out[root / "spill" / "empty.wal"].danger_err, SpillEmpty)
    assert not (root / "sessions").exists()


def test_parent_family_link_and_no_overwrite(tmp_path: Path) -> None:
    """A spill from a known session becomes the next version of its family with a parent link."""
    root, user, tmp = dirs(tmp_path)
    h = create_session(root, SessionMeta(slug="cu"), datetime(2026, 11, 8, tzinfo=UTC)).danger_ok
    parent_name = h.path.name
    suid = uuid.UUID(h.manifest.session_uuid)
    h.close()
    make_spill(root / "spill" / "s.wal", 1, 2, suid)
    rep = import_all_spills(root, user, tmp)[0][1].danger_ok
    assert rep is not None
    assert rep.parent == parent_name
    assert rep.version_dir.name.endswith(".v002")
    assert (root / "sessions" / parent_name).is_dir()


# frob:ticket 01M729648PC6N7FK6D2J6H1ETV
def _parent_with_records(root: Path, n: int, state: str = "incomplete") -> tuple[Path, uuid.UUID]:
    """Create a parent session with n durable NOTE records (writer closed) and return it."""
    h = create_session(root, SessionMeta(slug="cu"), datetime(2026, 11, 8, tzinfo=UTC)).danger_ok
    suid = uuid.UUID(h.manifest.session_uuid)
    w = WalWriter.open(h.path / "wal", suid, 1, WalConfig()).danger_ok
    for i in range(n):
        assert w.append(NewRecord(type=NOTE, payload=b"p" * 8 + bytes([i]))).is_ok
    w.close()
    h.close(state)
    return h.path, suid


# frob:tests python/sadi/store/spill.py::import_spill
def test_import_joins_parent_records_and_spill(tmp_path: Path) -> None:
    """The successor holds the parent's verified records plus the spill; parent is untouched."""
    root, user, tmp = dirs(tmp_path)
    parent, suid = _parent_with_records(root, 3)
    before = sorted((parent / "wal").glob("*.wal"))[0].read_bytes()
    make_spill(root / "spill" / "s.wal", 4, 2, suid)
    rep = import_all_spills(root, user, tmp)[0][1].danger_ok
    assert rep is not None and rep.continuity_ok is True
    recs = [r.danger_ok for r in WalReader(rep.version_dir / "wal").records()]
    assert [r.seq for r in recs] == [1, 2, 3, 4, 5]
    assert [r.payload[8] for r in recs[:3]] == [0, 1, 2]
    assert recs[3].payload == bytes([0]) * 20
    assert read_manifest(rep.version_dir).danger_ok.last_seq == 5
    assert sorted((parent / "wal").glob("*.wal"))[0].read_bytes() == before


# frob:tests python/sadi/store/spill.py::import_spill
def test_non_continuing_spill_stays_fragment(tmp_path: Path) -> None:
    """A spill that does not directly continue the parent is kept alone, never dropped."""
    root, user, tmp = dirs(tmp_path)
    _parent, suid = _parent_with_records(root, 3)
    make_spill(root / "spill" / "s.wal", 10, 2, suid)
    rep = import_all_spills(root, user, tmp)[0][1].danger_ok
    assert rep is not None and rep.continuity_ok is False
    assert WalReader.scan(rep.version_dir / "wal").danger_ok.record_count == 2


# frob:tests python/sadi/store/spill.py::write_spill
def test_write_spill_retry_is_idempotent_and_never_overwrites(tmp_path: Path) -> None:
    """Same records twice reuse one file; different records for the same key keep both."""
    root, user, tmp = dirs(tmp_path)
    suid = uuid.uuid4()
    recs = [Record(type=NOTE, seq=s, wall_ns=1, flags=0, payload=b"a" * 8, crc=0) for s in (4, 5)]
    first = write_spill(recs, suid, root, user, tmp).danger_ok
    again = write_spill(recs, suid, root, user, tmp).danger_ok
    assert first == again and len(list((root / "spill").glob("*.wal"))) == 1
    more = [*recs, Record(type=NOTE, seq=6, wall_ns=1, flags=0, payload=b"a" * 8, crc=0)]
    third = write_spill(more, suid, root, user, tmp).danger_ok
    assert third != first
    assert len(list((root / "spill").glob("*.wal"))) == 2
    assert first[0].exists()


# frob:tests python/sadi/store/spill.py::import_all_spills
def test_identical_spills_in_two_locations_import_once(tmp_path: Path) -> None:
    """Byte-identical spill copies in two locations yield a single new version."""
    root, user, tmp = dirs(tmp_path)
    _parent, suid = _parent_with_records(root, 3)
    data = make_spill(root / "spill" / "a.wal", 4, 2, suid)
    (user / "spill").mkdir(parents=True)
    (user / "spill" / "b.wal").write_bytes(data)
    out = import_all_spills(root, user, tmp)
    assert [o[1].danger_ok is not None for o in out] == [True, False]
    assert len(list((root / "sessions").iterdir())) == 2
