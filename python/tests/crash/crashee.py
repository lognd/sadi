"""Writer subprocess killed by the harness: a real session + WAL + snapshots + manifest churn.

Usage: python crashee.py <root> <oracle> <seed> <max_records> <segment_bytes>

Every acknowledged seq, committed snapshot (with sha256) and fsync offset is appended to the
oracle file (outside the session root) one line at a time, so the harness knows what the
store promised before it was killed.
"""

from __future__ import annotations

import hashlib
import os
import random
import sys
import threading
import uuid
from pathlib import Path

from sadi.logging_setup import get_logger
from sadi.store import events, snapshot
from sadi.store.manifest import write_manifest
from sadi.store.records import (
    MarkerV1,
    NewRecord,
    RecordType,
    SessionStartV1,
    encode_raw_block,
    json_record,
)
from sadi.store.session import SessionMeta, create_session
from sadi.store.wal import WalConfig, WalWriter

_log = get_logger("crashee")

PACKET_LEN = 612
SNAPSHOT_EVERY = 6
MANIFEST_EVERY = 4


def block_payload(seed: int, seq: int, packets: int) -> bytes:
    """Return the deterministic RAW_BLOCK payload the writer must have stored for `seq`."""
    stream = bytearray()
    counter = 0
    while len(stream) < packets * PACKET_LEN:
        stream += hashlib.sha256(f"{seed}:{seq}:{counter}".encode()).digest()
        counter += 1
    return encode_raw_block(bytes(stream[: packets * PACKET_LEN]), PACKET_LEN, seq, seq, seq)


def block_packets(seq: int) -> int:
    """Return how many packets the block at `seq` carries (1..3, a pure function of seq)."""
    return 1 + seq % 3


class Oracle:
    """Append-only, thread-safe, unbuffered oracle log (survives SIGKILL of this process)."""

    def __init__(self, path: Path) -> None:
        """Open `path` for append."""
        # frob:ticket 01M700BKTA0N0NYKWBDG24R9GM
        # O_BINARY: no LF->CRLF translation on Windows (it corrupted the digests).
        self._fd = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
        )
        self._lock = threading.Lock()

    def line(self, text: str) -> None:
        """Write one whole line with a single os.write."""
        with self._lock:
            os.write(self._fd, (text + "\n").encode("ascii"))


def _make_record(seed: int, seq: int) -> NewRecord:
    """Build the record for logical index `seq` (not the WAL seq; SEALs shift those)."""
    if seq % 5 == 0:
        return json_record(RecordType.MARKER, MarkerV1(kind="mark", label=f"m{seq}", raw_seq=seq))
    return NewRecord(
        type=int(RecordType.RAW_BLOCK), payload=block_payload(seed, seq, block_packets(seq))
    )


def main(argv: list[str]) -> int:
    """Run the scenario until `max_records` or until killed; return the exit code."""
    root, oracle_path = Path(argv[1]), Path(argv[2])
    seed, max_records, seg_bytes = int(argv[3]), int(argv[4]), int(argv[5])
    oracle = Oracle(oracle_path)
    rng = random.Random(seed)
    created = create_session(root, SessionMeta(slug="crash", lab_module="sadi.crash"))
    if created.is_err:
        _log.error("create_session failed: %s", created.danger_err)
        return 2
    handle = created.danger_ok
    wal_dir = handle.path / "wal"
    oracle.line(f"started {handle.path}")
    sid = uuid.UUID(handle.manifest.session_uuid)
    opened = WalWriter.open(wal_dir, sid, 1, WalConfig(segment_max_bytes=seg_bytes))
    if opened.is_err:
        _log.error("WAL open failed: %s", opened.danger_err)
        return 2
    writer = opened.danger_ok

    def on_fsync(_ms: float) -> None:
        """Record the active segment's size right after each flush (power-loss oracle)."""
        segs = sorted(p for p in wal_dir.iterdir() if p.name.startswith("seg-"))
        last = segs[-1]
        oracle.line(f"fsync_offset {last.name} {last.stat().st_size}")

    writer.set_fsync_observer(on_fsync)
    start = json_record(RecordType.SESSION_START, SessionStartV1(session_uuid=str(sid)))
    first = writer.append(start)
    if first.is_err:
        return 3
    oracle.line("ack 1")
    seq = 1
    index = 1  # logical record ordinal; WAL seqs also count SEAL records
    batches = 0
    while index < max_records:
        n = rng.randint(1, 4)
        recs = [_make_record(seed, index + 1 + i) for i in range(n)]
        index += n
        res = writer.append_batch(recs)
        if res.is_err:
            _log.error("append failed: %s", res.danger_err)
            return 3
        seq = res.danger_ok
        oracle.line(f"ack {seq}")
        batches += 1
        if batches % SNAPSHOT_EVERY == 0:
            state = events.replay_wal(wal_dir)
            if state.is_ok and state.danger_ok.covers_seq > 0:
                snap = snapshot.write_snapshot(handle, state.danger_ok, state.danger_ok.covers_seq)
                if snap.is_ok:
                    digest = hashlib.sha256(snap.danger_ok.read_bytes()).hexdigest()
                    oracle.line(f"snapshot {snap.danger_ok.name} {digest}")
        if batches % MANIFEST_EVERY == 0:
            mf = handle.manifest.model_copy(update={"last_seq": seq})
            if write_manifest(handle.path, mf).is_ok:
                oracle.line(f"manifest {seq}")
    writer.close()
    handle.close()
    oracle.line("clean_exit")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
