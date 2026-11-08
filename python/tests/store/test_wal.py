"""Tests for the WAL: group commit, rotation, recovery classification, crashes, properties."""

from __future__ import annotations

import hashlib
import os
import statistics
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sadi.store import failpoints
from sadi.store.records import (
    FLAG_JSON,
    MarkerV1,
    NewRecord,
    Record,
    RecordType,
    SessionStartV1,
    SettingsV1,
    decode_frame,
    decode_raw_junk,
    decode_seal,
    encode_frame,
    encode_raw_block,
    encode_raw_junk,
    encode_seal,
    json_record,
)
from sadi.store.wal import (
    SEGMENT_HEADER_LEN,
    WalConfig,
    WalCorrupt,
    WalInvalidRecord,
    WalReader,
    WalWriter,
    segment_name,
)

SESSION = uuid.UUID(int=0x5AD1)


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    """Clear failpoints around each test."""
    failpoints.clear()
    yield
    failpoints.clear()


def _open(tmp_path: Path, **cfg: int) -> WalWriter:
    """Open a writer in tmp_path/wal with optional config overrides."""
    wal = tmp_path / "wal"
    wal.mkdir(exist_ok=True)
    res = WalWriter.open(wal, SESSION, 1, WalConfig(**cfg))
    assert res.is_ok, res
    return res.danger_ok


def _rec(n: int, size: int = 16) -> NewRecord:
    """Build a small NOTE-typed binary-ish record."""
    return NewRecord(type=int(RecordType.NOTE), payload=bytes([n % 256]) * size)


def _read_all(wal: Path) -> list[bytes]:
    """Return payloads of all verified records."""
    return [r.danger_ok.payload for r in WalReader(wal).records() if r.is_ok]


# frob:ticket 01M6W7R1VQHABR51SH64668M06
# frob:tests python/sadi/store/wal.py::WalWriter.append
def test_append_assigns_dense_seq_and_is_durable(tmp_path: Path) -> None:
    """Appends return dense seqs; durable_seq has reached them when append returns."""
    w = _open(tmp_path)
    seqs = []
    for i in range(10):
        r = w.append(_rec(i))
        assert r.is_ok
        seqs.append(r.danger_ok)
        assert w.durable_seq >= r.danger_ok
    assert seqs == list(range(1, 11))
    assert w.close().is_ok
    assert len(_read_all(tmp_path / "wal")) == 10


# frob:tests python/sadi/store/wal.py::WalWriter.append_nowait
def test_group_commit_batches_many_records_per_fsync(tmp_path: Path) -> None:
    """Many nowait appends are covered by far fewer fsync batches."""
    w = _open(tmp_path)
    last = 0
    for i in range(500):
        last = w.append_nowait(_rec(i)).danger_ok
    assert w.wait_durable(last, 10).is_ok
    stats = w.stats()
    assert stats.durable_seq == last
    assert stats.batches < 500
    assert w.close().is_ok


def test_durable_seq_only_after_fsync(tmp_path: Path) -> None:
    """With the fsync failpoint sleeping, durable_seq must lag the enqueue."""
    failpoints.configure({"wal.fsync.before": "sleep:300"})
    w = _open(tmp_path)
    seq = w.append_nowait(_rec(1)).danger_ok
    time.sleep(0.05)
    assert w.durable_seq < seq
    assert w.wait_durable(seq, 5).is_ok
    assert w.durable_seq >= seq
    assert w.close().is_ok


def test_invalid_records_refused(tmp_path: Path) -> None:
    """Producers cannot write SEAL, reserved types or oversize payloads."""
    w = _open(tmp_path, max_payload=8)
    for bad in (
        NewRecord(type=int(RecordType.SEAL), payload=b""),
        NewRecord(type=0, payload=b""),
        NewRecord(type=int(RecordType.NOTE), payload=b"x" * 9),
        NewRecord(type=int(RecordType.RAW_JUNK), payload=b"", flags=FLAG_JSON),
    ):
        r = w.append(bad)
        assert r.is_err and isinstance(r.danger_err, WalInvalidRecord)
    assert w.close().is_ok


def test_closed_writer_refuses(tmp_path: Path) -> None:
    """After close, append returns Err."""
    w = _open(tmp_path)
    assert w.close().is_ok
    assert w.append(_rec(0)).is_err


# frob:tests python/sadi/store/wal.py::WalWriter.rotate
def test_rotation_seals_segments_and_reads_back(tmp_path: Path) -> None:
    """Small segments rotate with seals; the reader sees every record in order."""
    w = _open(tmp_path, segment_max_bytes=2048)
    for i in range(100):
        assert w.append(_rec(i, 64)).is_ok
    assert w.close().is_ok
    wal = tmp_path / "wal"
    files = sorted(p.name for p in wal.iterdir())
    assert len(files) > 3 and files[0] == segment_name(1)
    rep = WalReader.scan(wal)
    assert rep.is_ok
    report = rep.danger_ok
    assert report.record_count == 100 and report.tail is None
    assert all(s.sealed for s in report.segments[:-1])
    assert not report.segments[-1].sealed
    assert _read_all(wal) == [bytes([i]) * 64 for i in range(100)]


def test_explicit_rotate(tmp_path: Path) -> None:
    """rotate() seals and starts a new segment."""
    w = _open(tmp_path)
    assert w.append(_rec(1)).is_ok
    assert w.rotate().is_ok
    assert w.append(_rec(2)).is_ok
    assert w.close().is_ok
    rep = WalReader.scan(tmp_path / "wal").danger_ok
    assert [s.sealed for s in rep.segments] == [True, False]
    assert rep.record_count == 2


def test_typed_records_roundtrip(tmp_path: Path) -> None:
    """SESSION_START, SETTINGS, MARKER, RAW_BLOCK and RAW_JUNK survive the WAL intact."""
    w = _open(tmp_path)
    recs = [
        json_record(RecordType.SESSION_START, SessionStartV1(session_uuid=str(SESSION))),
        json_record(RecordType.SETTINGS, SettingsV1(scope="adc", key="range", value=2)),
        NewRecord(
            type=int(RecordType.RAW_BLOCK),
            payload=encode_raw_block(b"\x01" * 40, 20, 5, 6, 7),
        ),
        NewRecord(type=int(RecordType.RAW_JUNK), payload=encode_raw_junk(9, 1, b"zz")),
        json_record(RecordType.MARKER, MarkerV1(kind="mark", label="a")),
    ]
    for r in recs:
        assert w.append(r).is_ok
    assert w.close().is_ok
    got = [r.danger_ok for r in WalReader(tmp_path / "wal").records()]
    assert [g.payload for g in got] == [r.payload for r in recs]
    junk = decode_raw_junk(got[3].payload)
    assert junk.is_ok and junk.danger_ok.data == b"zz"


# frob:tests python/sadi/store/wal.py::WalReader.scan
def test_torn_tail_reported_not_truncated(tmp_path: Path) -> None:
    """A partial last frame is reported with offset, length and SHA-256 and left in place."""
    w = _open(tmp_path)
    for i in range(5):
        assert w.append(_rec(i)).is_ok
    assert w.close().is_ok
    seg = tmp_path / "wal" / segment_name(1)
    good = seg.stat().st_size
    junk = encode_frame(int(RecordType.NOTE), 6, 1, 0, b"abcdefgh")[:-5]
    with seg.open("ab") as f:
        f.write(junk)
    before = seg.read_bytes()
    rep = WalReader.scan(tmp_path / "wal").danger_ok
    assert rep.record_count == 5
    assert rep.tail is not None
    assert (rep.tail.offset, rep.tail.length) == (good, len(junk))
    assert rep.tail.sha256 == hashlib.sha256(junk).hexdigest()
    assert seg.read_bytes() == before


# frob:tests python/sadi/store/wal.py::WalReader.records
def test_mid_log_bad_crc_rejected_not_skipped(tmp_path: Path) -> None:
    """A flipped bit in a middle record is an Err after the verified prefix, never skipped."""
    w = _open(tmp_path)
    for i in range(10):
        assert w.append(_rec(i)).is_ok
    assert w.close().is_ok
    seg = tmp_path / "wal" / segment_name(1)
    data = bytearray(seg.read_bytes())
    frame = 32 + 16
    data[SEGMENT_HEADER_LEN + frame * 4 + 40] ^= 0x01
    seg.write_bytes(bytes(data))
    out = list(WalReader(tmp_path / "wal").records())
    oks = [r for r in out if r.is_ok]
    assert len(oks) == 4
    assert out[-1].is_err and isinstance(out[-1].danger_err, WalCorrupt)
    assert out[-1].danger_err.offset == SEGMENT_HEADER_LEN + frame * 4
    assert WalReader.scan(tmp_path / "wal").is_err


def test_missing_middle_segment_is_corrupt(tmp_path: Path) -> None:
    """A deleted middle segment is a gap error."""
    w = _open(tmp_path, segment_max_bytes=1024)
    for i in range(60):
        assert w.append(_rec(i, 64)).is_ok
    assert w.close().is_ok
    (tmp_path / "wal" / segment_name(2)).unlink()
    assert WalReader.scan(tmp_path / "wal").is_err


# ---- failpoint-driven crashes --------------------------------------------------------------


def test_fsync_error_enters_failed_and_keeps_undurable(tmp_path: Path) -> None:
    """An fsync failure fails the writer; the record stays in memory and is not durable."""
    w = _open(tmp_path)
    assert w.append(_rec(0)).is_ok
    failpoints.configure({"wal.fsync.before": "once:error:5"})
    r = w.append(_rec(1))
    assert r.is_err
    assert w.state == "FAILED"
    assert w.durable_seq == 1
    assert [x.seq for x in w.undurable_records()] == [2]
    assert w.append(_rec(2)).is_err
    w.close()


_CRASH_SCRIPT = """
import sys, uuid
from pathlib import Path
from sadi.store.wal import WalWriter, WalConfig
from sadi.store.records import NewRecord
wal = Path(sys.argv[1])
w = WalWriter.open(wal, uuid.UUID(int=1), 1, WalConfig(segment_max_bytes=1500)).danger_ok
for i in range(200):
    w.append(NewRecord(type=8, payload=bytes([i % 256]) * 40))
w.close()
"""


@pytest.mark.parametrize(
    "spec",
    [
        "wal.write.partial=nth:5:kill",
        "wal.write.after=nth:7:kill",
        "wal.fsync.before=nth:9:kill",
        "wal.fsync.after=nth:11:kill",
        "wal.rotate.after_seal_write=once:kill",
        "wal.rotate.after_create=once:kill",
        "wal.rotate.after_header=once:kill",
        "wal.rotate.after_header_fsync=once:kill",
    ],
)
def test_kill_at_failpoint_leaves_recoverable_log(tmp_path: Path, spec: str) -> None:
    """Killing the process at any step leaves a log that scans without corruption."""
    wal = tmp_path / "wal"
    wal.mkdir()
    name, _, action = spec.partition("=")
    env = dict(os.environ, SADI_FAILPOINTS=f"{name}={action}")
    proc = subprocess.run(
        [sys.executable, "-c", _CRASH_SCRIPT, str(wal)], env=env, capture_output=True, timeout=60
    )
    assert proc.returncode == 137, proc.stderr.decode()
    rep = WalReader.scan(wal)
    assert rep.is_ok, rep
    report = rep.danger_ok
    payloads = _read_all(wal)
    assert payloads == [bytes([i % 256]) * 40 for i in range(len(payloads))]
    assert report.last_seq is None or report.record_count >= 1 or report.tail is not None


# ---- properties ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_log(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, bytes, list[bytes]]:
    """A one-segment log: (dir, segment bytes, payloads)."""
    d = tmp_path_factory.mktemp("sample")
    w = _open(d)
    for i in range(12):
        assert w.append(_rec(i, 20)).is_ok
    assert w.close().is_ok
    seg = d / "wal" / segment_name(1)
    return d / "wal", seg.read_bytes(), [bytes([i]) * 20 for i in range(12)]


def _scan_variant(tmp: Path, data: bytes) -> tuple[list[bytes], bool]:
    """Write `data` as segment 1 in a fresh dir and return (accepted payloads, had_error)."""
    d = Path(tmp)
    d.mkdir(parents=True, exist_ok=True)
    (d / segment_name(1)).write_bytes(data)
    out = list(WalReader(d).records())
    return [r.danger_ok.payload for r in out if r.is_ok], any(r.is_err for r in out)


# frob:tests python/sadi/store/wal.py::WalReader.records
@settings(
    max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(cut=st.integers(min_value=0, max_value=10_000))
def test_property_truncation_yields_only_a_prefix(
    sample_log: tuple[Path, bytes, list[bytes]], tmp_path_factory: pytest.TempPathFactory, cut: int
) -> None:
    """Any truncation accepts exactly a prefix of the original records."""
    _d, data, payloads = sample_log
    got, _err = _scan_variant(tmp_path_factory.mktemp("t"), data[: min(cut, len(data))])
    assert got == payloads[: len(got)]


# frob:tests python/sadi/store/wal.py::WalReader.records
@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(pos=st.integers(min_value=0, max_value=10_000), bit=st.integers(min_value=0, max_value=7))
def test_property_bit_flip_never_accepts_corrupt_record(
    sample_log: tuple[Path, bytes, list[bytes]],
    tmp_path_factory: pytest.TempPathFactory,
    pos: int,
    bit: int,
) -> None:
    """A single bit flip never yields an accepted record that differs from the original."""
    _d, data, payloads = sample_log
    i = pos % len(data)
    if i < SEGMENT_HEADER_LEN:
        return
    mutated = bytearray(data)
    mutated[i] ^= 1 << bit
    got, _err = _scan_variant(tmp_path_factory.mktemp("f"), bytes(mutated))
    assert got == payloads[: len(got)]
    assert len(got) < len(payloads)


def test_decode_frame_rejects_flip() -> None:
    """decode_frame refuses a flipped frame."""
    frame = bytearray(encode_frame(8, 1, 1, 0, b"hello"))
    assert decode_frame(bytes(frame)).is_ok
    frame[-1] ^= 1
    assert decode_frame(bytes(frame)).is_err


# ---- throughput ----------------------------------------------------------------------------


# frob:tests python/sadi/store/wal.py::WalWriter.append
def test_throughput_sustains_612_kbps_with_markers(tmp_path: Path) -> None:
    """Sustain 612 kB/s of raw blocks plus markers for 3 s and report p99 append latency."""
    w = _open(tmp_path)
    block = encode_raw_block(b"\x07" * 6120, 20, 1, 1, 0)
    raw = NewRecord(type=int(RecordType.RAW_BLOCK), payload=block)
    marker = json_record(RecordType.MARKER, MarkerV1(kind="m"))
    rate, secs, per_s = 612_000, 3.0, 100
    chunk = rate // per_s
    assert len(block) >= chunk
    lat: list[float] = []
    start = time.perf_counter()
    for tick in range(int(secs * per_s)):
        t0 = time.perf_counter()
        assert w.append(raw).is_ok
        if tick % 50 == 0:
            assert w.append(marker).is_ok
        lat.append(time.perf_counter() - t0)
        target = start + (tick + 1) / per_s
        time.sleep(max(0.0, target - time.perf_counter()))
    elapsed = time.perf_counter() - start
    assert w.close().is_ok
    lat.sort()
    p99 = lat[int(len(lat) * 0.99) - 1] * 1000
    print(f"p99 append latency {p99:.2f} ms median {statistics.median(lat) * 1000:.2f} ms")
    delivered = w.stats().durable_seq
    assert delivered >= int(secs * per_s)
    assert elapsed < secs * 1.5
    assert p99 < 250


# frob:tests python/sadi/store/wal.py::WalWriter.append_batch
# frob:tests python/sadi/store/wal.py::WalWriter.durable_seq
# frob:tests python/sadi/store/wal.py::WalWriter.enqueued_seq
# frob:tests python/sadi/store/wal.py::WalWriter.state
def test_append_batch_and_accessors(tmp_path: Path) -> None:
    """append_batch returns the last seq; accessors reflect state."""
    w = _open(tmp_path)
    assert w.state == "RUNNING"
    last = w.append_batch([_rec(i) for i in range(5)])
    assert last.danger_ok == 5
    assert w.durable_seq == 5 and w.enqueued_seq == 5
    assert w.close().is_ok
    assert w.state == "CLOSED"


# frob:tests python/sadi/store/records.py::Record.known
# frob:tests python/sadi/store/records.py::encode_seal
# frob:tests python/sadi/store/records.py::decode_seal
def test_record_known_and_seal_roundtrip() -> None:
    """Registered types are known; seal payloads roundtrip."""
    mk = lambda t: Record(type=t, seq=1, wall_ns=0, flags=0, payload=b"", crc=0)  # noqa: E731
    assert mk(int(RecordType.NOTE)).known and not mk(0x55).known
    seal = decode_seal(encode_seal(3, 1, 3, b"\x01" * 32))
    assert seal.is_ok and seal.danger_ok.record_count == 3


# frob:ticket 01M6WJQV8ZG969CCJ9XRGHGDN9
# frob:tests python/sadi/store/wal.py::WalReader.scan
@pytest.mark.parametrize("cut", [0, 5, 8, SEGMENT_HEADER_LEN - 1])
def test_torn_first_header_scans_as_empty(tmp_path: Path, cut: int) -> None:
    """A lone first segment with a short header holds no acks: Ok, empty, tail set, file kept."""
    w = _open(tmp_path)
    assert w.close().is_ok
    seg = tmp_path / "wal" / segment_name(1)
    seg.write_bytes(seg.read_bytes()[:cut])
    before = seg.read_bytes()
    rep = WalReader.scan(tmp_path / "wal").danger_ok
    assert rep.record_count == 0
    assert rep.tail is not None and (rep.tail.offset, rep.tail.length) == (0, cut)
    assert seg.read_bytes() == before
    assert list(WalReader(tmp_path / "wal").records()) == []


# frob:ticket 01M6WJQV8ZG969CCJ9XRGHGDN9
# frob:tests python/sadi/store/wal.py::WalReader.scan
def test_corrupt_first_header_stays_error(tmp_path: Path) -> None:
    """A full-length first header with a flipped bit, or non-magic short bytes, is still an Err."""
    w = _open(tmp_path)
    assert w.close().is_ok
    seg = tmp_path / "wal" / segment_name(1)
    good = seg.read_bytes()
    bad = bytearray(good[:SEGMENT_HEADER_LEN])
    bad[20] ^= 0x01
    seg.write_bytes(bytes(bad))
    assert WalReader.scan(tmp_path / "wal").is_err
    seg.write_bytes(b"XXXXXXXXXX")
    assert WalReader.scan(tmp_path / "wal").is_err
