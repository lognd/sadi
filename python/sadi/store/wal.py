"""Append-only checksummed fsynced WAL: group-commit writer, verifying reader, recovery scan.

Follows docs/data-safety.md sections 3-6 and 11. Recovery is a pure read: nothing is ever
truncated or modified; a torn tail is reported with offset, length and SHA-256.
"""

# frob:ticket 01M6W7R1VQHABR51SH64668M06
from __future__ import annotations

import hashlib
import re
import struct
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from crc32c import crc32c
from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result, propagate

from sadi.logging_setup import get_logger
from sadi.store import durable
from sadi.store.durable import DurableError, create_exclusive, fsync_dir
from sadi.store.failpoints import failpoint
from sadi.store.records import (
    FLAG_JSON,
    FRAME_HEADER_LEN,
    FRAME_MAGIC,
    KNOWN_FLAGS,
    MAX_PAYLOAD,
    SEAL_PAYLOAD_LEN,
    NewRecord,
    Record,
    RecordType,
    decode_payload_check,
    decode_seal,
    encode_frame,
    encode_seal,
    new_prefix_hash,
    parse_header,
    prefix_hash_update,
)

_log = get_logger(__name__)

Seq = int

SEGMENT_MAGIC = b"SADIWAL\x00"
SEGMENT_HEADER_LEN = 64
FORMAT_VERSION = 1
SUPPORTED_FORMATS = (1,)
CHECKSUM_CRC32C = 1
SEAL_FRAME_LEN = FRAME_HEADER_LEN + SEAL_PAYLOAD_LEN
BATCH_MAX_BYTES = 4 * 1024 * 1024
BATCH_MAX_RECORDS = 1024
SEGMENT_MAX_BYTES = 256 * 1024 * 1024
QUEUE_MAX_BYTES = 64 * 1024 * 1024
QUEUE_MAX_ITEMS = 65536
SLOW_FSYNC_MS = 100.0

# magic8 fmt(H) algo(B) res(B) segno(I) first_seq(Q) uuid16 created_ns(q) res12 crc(I)
_SEG_HEAD_NO_CRC = struct.Struct("<8sHBBIQ16sq12s")
_SEG_NAME = re.compile(r"^seg-(\d{6})\.wal$")
_SCAN_CHUNK = 1024 * 1024


def segment_name(segment_no: int) -> str:
    """Return the file name of segment `segment_no` (`seg-NNNNNN.wal`)."""
    return f"seg-{segment_no:06d}.wal"


# ---- errors ----------------------------------------------------------------------------


class WalError(BaseModel):
    """Base of all WAL failures; `hint` is shown in the UI."""

    model_config = ConfigDict(frozen=True)
    hint: str = ""


class WalCorrupt(WalError):
    """A bad record or structure that is not a torn tail; never skipped (I3, I9)."""

    segment: int
    offset: int
    reason: str
    prefix_last_seq: int = 0
    prefix_records: int = 0
    hint: str = "The recording is damaged; the verified part can still be viewed and exported."


class WalUnsupportedFormat(WalError):
    """A segment declares a format version this build cannot read."""

    found: int
    supported: tuple[int, ...] = SUPPORTED_FORMATS
    hint: str = "This recording was written by a newer version of the software."


class WalSegmentHeaderInvalid(WalError):
    """A segment header failed verification (segment is None when no segment exists)."""

    segment: int | None
    reason: str
    hint: str = "The recording's segment header is damaged or missing."


class WalDurable(WalError):
    """A durability primitive failed."""

    error: DurableError
    hint: str = "A disk error occurred while saving; see the log."


class WalInvalidRecord(WalError):
    """The caller supplied a record the WAL refuses to write (programmer error upstream)."""

    reason: str


class WalClosed(WalError):
    """The writer is closed or draining and accepts no new records."""

    hint: str = "The recording is closed."


class WalFailed(WalError):
    """The writer entered FAILED after an I/O error; undurable records are kept in memory."""

    reason: str
    errno: int | None = None
    hint: str = "Saving failed. Data already shown is safe; free disk space and retry."


class WalTimeout(WalError):
    """A wait for durability or queue space timed out."""

    what: str
    waited_s: float
    hint: str = "The data disk is not responding."


class WalInternal(WalError):
    """An unexpected exception in the writer thread (a bug)."""

    detail: str


class WalConfig(BaseModel):
    """Writer tunables (section 6.2); tests shrink them to force batching and rotation."""

    model_config = ConfigDict(frozen=True)
    batch_max_bytes: int = BATCH_MAX_BYTES
    batch_max_records: int = BATCH_MAX_RECORDS
    segment_max_bytes: int = SEGMENT_MAX_BYTES
    max_payload: int = MAX_PAYLOAD
    queue_max_bytes: int = QUEUE_MAX_BYTES
    queue_max_items: int = QUEUE_MAX_ITEMS
    submit_timeout_s: float = 2.0
    durable_timeout_s: float = 30.0


class WalStats(BaseModel):
    """Snapshot of writer counters (a subset of the section 7.2 metrics)."""

    model_config = ConfigDict(frozen=True)
    state: str
    enqueued_seq: int
    durable_seq: int
    queue_depth_items: int
    queue_depth_bytes: int
    segment_no: int
    segment_bytes: int
    batches: int
    last_batch_records: int
    last_fsync_ms: float
    max_fsync_ms: float
    rotations: int


def _hit(name: str) -> Result[None, WalError]:
    """Hit failpoint `name`, mapping an injected OSError to a WalFailed error."""
    try:
        failpoint(name)
    except OSError as exc:
        _log.error("failpoint %s raised %s", name, exc)
        return Err(WalFailed(reason=f"failpoint {name}: {exc}", errno=exc.errno))
    return Ok(None)


def _durable_err(err: DurableError) -> WalError:
    """Wrap a DurableError as a WalDurable."""
    return WalDurable(error=err)


# ---- segment header ----------------------------------------------------------------------


class SegmentHeader(BaseModel):
    """Decoded 64-byte segment header (section 4.1)."""

    model_config = ConfigDict(frozen=True)
    format_version: int
    checksum_algo: int
    segment_no: int
    first_seq: int
    session_uuid: uuid.UUID
    created_ns: int


def encode_segment_header(segment_no: int, first_seq: int, session_uuid: uuid.UUID) -> bytes:
    """Encode the 64-byte segment header with its trailing CRC-32C."""
    head = _SEG_HEAD_NO_CRC.pack(
        SEGMENT_MAGIC,
        FORMAT_VERSION,
        CHECKSUM_CRC32C,
        0,
        segment_no,
        first_seq,
        session_uuid.bytes,
        time.time_ns(),
        b"\x00" * 12,
    )
    return head + struct.pack("<I", crc32c(head))


def decode_segment_header(data: bytes, segment: int) -> Result[SegmentHeader, WalError]:
    """Verify and decode a segment header read from file number `segment`."""
    if len(data) < SEGMENT_HEADER_LEN:
        return Err(WalSegmentHeaderInvalid(segment=segment, reason="header shorter than 64 bytes"))
    magic, fmt, algo, _res, seg_no, first_seq, uuid_b, created, _res2 = _SEG_HEAD_NO_CRC.unpack(
        data[:60]
    )
    if magic != SEGMENT_MAGIC:
        return Err(WalSegmentHeaderInvalid(segment=segment, reason="bad segment magic"))
    (crc,) = struct.unpack("<I", data[60:64])
    if crc32c(data[:60]) != crc:
        return Err(WalSegmentHeaderInvalid(segment=segment, reason="segment header CRC mismatch"))
    if fmt not in SUPPORTED_FORMATS:
        return Err(WalUnsupportedFormat(found=fmt))
    if algo != CHECKSUM_CRC32C:
        return Err(WalSegmentHeaderInvalid(segment=segment, reason=f"unknown checksum {algo}"))
    return Ok(
        SegmentHeader(
            format_version=fmt,
            checksum_algo=algo,
            segment_no=seg_no,
            first_seq=first_seq,
            session_uuid=uuid.UUID(bytes=uuid_b),
            created_ns=created,
        )
    )


# ---- writer ------------------------------------------------------------------------------


class _Done:
    """One-shot completion carrying a Result for rotate() and close()."""

    def __init__(self) -> None:
        """Create an unset completion."""
        self.event = threading.Event()
        self.result: Result[None, WalError] = Ok(None)

    def set(self, result: Result[None, WalError]) -> None:
        """Publish `result` and wake the waiter."""
        self.result = result
        self.event.set()


@dataclass
class _Rotate:
    """Queue item: seal the current segment using `seal_seq` and start the next."""

    seal_seq: int
    done: _Done | None = None


@dataclass
class _Stop:
    """Queue item: flush everything before it, close the segment and end the thread."""

    done: _Done = field(default_factory=_Done)


_Item = Record | _Rotate | _Stop


def _item_size(item: _Item) -> int:
    """Return the queue byte cost of an item (frame size for records, 0 for control)."""
    return FRAME_HEADER_LEN + len(item.payload) if isinstance(item, Record) else 0


class WalWriter:
    """Group-commit WAL writer: a dedicated thread owns the segment fd; callers enqueue.

    `append` blocks until the record is durable (the documented durable gate);
    `append_nowait` returns the seq at enqueue and `wait_durable` is the gate.
    """

    def __init__(
        self,
        wal_dir: Path,
        session_uuid: uuid.UUID,
        first_seq: int,
        config: WalConfig,
        fd: int,
    ) -> None:
        """Take ownership of segment 1's open fd; use `WalWriter.open` instead of this."""
        self._dir = wal_dir
        self._uuid = session_uuid
        self._cfg = config
        self._cv = threading.Condition()
        self._queue: deque[_Item] = deque()
        self._queued_bytes = 0
        self._next_seq = first_seq
        self._durable_seq = first_seq - 1
        self._proj_bytes = SEGMENT_HEADER_LEN
        self._proj_records = 0
        self._state = "RUNNING"
        self._error: WalError | None = None
        self._undurable: list[Record] = []
        self._pending_dones: list[_Done] = []
        # writer-thread-only state
        self._fd = fd
        self._seg_no = 1
        self._seg_first_seq = first_seq
        self._seg_records = 0
        self._seg_bytes = SEGMENT_HEADER_LEN
        self._seg_hash = hashlib.sha256()
        # metrics (guarded by _cv)
        self._batches = 0
        self._last_batch = 0
        self._last_fsync_ms = 0.0
        self._max_fsync_ms = 0.0
        self._rotations = 0
        self._fsync_observer: Callable[[float], None] | None = None
        self._failure_observer: Callable[[WalError], None] | None = None
        self._thread = threading.Thread(target=self._run, name="sadi-wal-writer", daemon=False)

    @staticmethod
    def open(
        wal_dir: Path,
        session_uuid: uuid.UUID,
        first_seq: int = 1,
        config: WalConfig | None = None,
    ) -> Result[WalWriter, WalError]:
        """Create segment 1 exclusively in `wal_dir`, fsync file and dir, start the thread."""
        cfg = config or WalConfig()
        path = wal_dir / segment_name(1)
        created = create_exclusive(path)
        if created.is_err:
            return Err(WalDurable(error=created.danger_err))
        fd = created.danger_ok
        header = encode_segment_header(1, first_seq, session_uuid)
        try:
            _write_all(fd, header)
        except OSError as exc:
            durable_close(fd)
            _log.error("writing header of %s failed: %s", path, exc)
            return Err(WalFailed(reason=f"header write: {exc}", errno=exc.errno))
        synced = durable.fsync_file(fd)
        if synced.is_err:
            durable_close(fd)
            return Err(WalDurable(error=synced.danger_err))
        synced_dir = fsync_dir(wal_dir)
        if synced_dir.is_err:
            durable_close(fd)
            return Err(WalDurable(error=synced_dir.danger_err))
        writer = WalWriter(wal_dir, session_uuid, first_seq, cfg, fd)
        writer._seg_hash.update(header)
        writer._thread.start()
        _log.info("WAL opened at %s first_seq=%d session=%s", path, first_seq, session_uuid)
        return Ok(writer)

    # -- producer side ---------------------------------------------------------------------

    def append_nowait(self, record: NewRecord) -> Result[Seq, WalError]:
        """Enqueue `record`, returning its assigned seq without waiting for durability."""
        invalid = self._validate(record)
        if invalid is not None:
            _log.error("append refused: %s", invalid.reason)
            return Err(invalid)
        size = FRAME_HEADER_LEN + len(record.payload)
        deadline = time.monotonic() + self._cfg.submit_timeout_s
        with self._cv:
            while True:
                refused = self._refusal()
                if refused is not None:
                    return Err(refused)
                if self._has_space(size):
                    break
                left = deadline - time.monotonic()
                if left <= 0:
                    _log.error(
                        "append backpressure: queue full for %.1fs", self._cfg.submit_timeout_s
                    )
                    return Err(WalTimeout(what="queue space", waited_s=self._cfg.submit_timeout_s))
                self._cv.wait(left)
            if (
                self._proj_records > 0
                and self._proj_bytes + size + SEAL_FRAME_LEN > self._cfg.segment_max_bytes
            ):
                self._enqueue_rotate_locked(None)
            seq = self._next_seq
            self._next_seq += 1
            self._proj_bytes += size
            self._proj_records += 1
            rec = Record(
                type=record.type,
                seq=seq,
                wall_ns=time.time_ns(),
                flags=record.flags,
                payload=record.payload,
                crc=0,
            )
            self._queue.append(rec)
            self._queued_bytes += size
            self._cv.notify_all()
        return Ok(seq)

    def append(self, record: NewRecord) -> Result[Seq, WalError]:
        """Enqueue `record` and block until it is durable; return its seq."""
        seq = self.append_nowait(record)
        if seq.is_err:
            return seq
        waited = self.wait_durable(seq.danger_ok, self._cfg.durable_timeout_s)
        if waited.is_err:
            return Err(waited.danger_err)
        return seq

    def append_batch(self, records: Sequence[NewRecord]) -> Result[Seq, WalError]:
        """Enqueue every record in order, wait for the last to be durable, return its seq."""
        last: Seq = self._durable_seq
        for rec in records:
            r = self.append_nowait(rec)
            if r.is_err:
                return r
            last = r.danger_ok
        waited = self.wait_durable(last, self._cfg.durable_timeout_s)
        if waited.is_err:
            return Err(waited.danger_err)
        return Ok(last)

    def wait_durable(self, seq: Seq, timeout_s: float | None) -> Result[None, WalError]:
        """Block until `durable_seq >= seq` (the display gate), the writer fails, or timeout."""
        deadline = None if timeout_s is None else time.monotonic() + timeout_s
        with self._cv:
            while self._durable_seq < seq:
                if self._error is not None:
                    return Err(self._error)
                left = None if deadline is None else deadline - time.monotonic()
                if left is not None and left <= 0:
                    _log.error("wait_durable(%d) timed out after %.1fs", seq, timeout_s or 0.0)
                    return Err(WalTimeout(what=f"durable seq {seq}", waited_s=timeout_s or 0.0))
                self._cv.wait(left)
        return Ok(None)

    def rotate(self) -> Result[None, WalError]:
        """Seal the active segment and start the next; blocks until the new segment is durable."""
        done = _Done()
        with self._cv:
            refused = self._refusal()
            if refused is not None:
                return Err(refused)
            self._enqueue_rotate_locked(done)
            self._cv.notify_all()
        done.event.wait()
        return done.result

    def close(self) -> Result[None, WalError]:
        """Drain the queue, fsync, leave the last segment unsealed, stop the thread."""
        with self._cv:
            if self._state in ("CLOSED", "FAILED"):
                err = self._error
            elif self._state == "DRAINING":
                err = None
            else:
                self._set_state_locked("DRAINING")
                stop = _Stop()
                self._queue.append(stop)
                self._cv.notify_all()
                err = None
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join()
        if err is not None:
            return Err(err)
        with self._cv:
            return Err(self._error) if self._error is not None else Ok(None)

    @property
    def durable_seq(self) -> Seq:
        """Highest seq whose bytes were fsynced (monotonic; published after fsync only)."""
        with self._cv:
            return self._durable_seq

    @property
    def enqueued_seq(self) -> Seq:
        """Highest seq assigned so far (including seals)."""
        with self._cv:
            return self._next_seq - 1

    @property
    def state(self) -> str:
        """Writer state: RUNNING, DRAINING, CLOSED or FAILED."""
        with self._cv:
            return self._state

    def set_fsync_observer(self, observer: Callable[[float], None] | None) -> None:
        """Install a callback receiving each successful fsync latency in ms (writer thread)."""
        with self._cv:
            self._fsync_observer = observer

    def set_failure_observer(self, observer: Callable[[WalError], None] | None) -> None:
        """Install a callback run once on the writer thread when the writer enters FAILED."""
        with self._cv:
            self._failure_observer = observer

    def undurable_records(self) -> list[Record]:
        """Return records kept in memory after FAILED that are not known durable (in order)."""
        with self._cv:
            return list(self._undurable) + [i for i in self._queue if isinstance(i, Record)]

    def stats(self) -> WalStats:
        """Return a snapshot of the writer counters."""
        with self._cv:
            return WalStats(
                state=self._state,
                enqueued_seq=self._next_seq - 1,
                durable_seq=self._durable_seq,
                queue_depth_items=len(self._queue),
                queue_depth_bytes=self._queued_bytes,
                segment_no=self._seg_no,
                segment_bytes=self._seg_bytes,
                batches=self._batches,
                last_batch_records=self._last_batch,
                last_fsync_ms=self._last_fsync_ms,
                max_fsync_ms=self._max_fsync_ms,
                rotations=self._rotations,
            )

    # -- producer helpers (call with _cv held where noted) ----------------------------------

    def _validate(self, record: NewRecord) -> WalInvalidRecord | None:
        """Return an error if the record may not be written by a producer."""
        if record.type <= 0 or record.type >= 0x80 or record.type in (RecordType.SEAL,):
            return WalInvalidRecord(reason=f"record type {record.type:#x} not writable")
        if record.flags & ~KNOWN_FLAGS or record.flags & 0x2:
            return WalInvalidRecord(reason=f"flags {record.flags:#x} not allowed")
        if len(record.payload) > self._cfg.max_payload:
            return WalInvalidRecord(reason=f"payload {len(record.payload)} bytes too large")
        is_binary = record.type in (RecordType.RAW_BLOCK, RecordType.RAW_JUNK)
        if is_binary and record.flags & FLAG_JSON:
            return WalInvalidRecord(reason="binary record type with JSON flag")
        return None

    def _refusal(self) -> WalError | None:
        """Return the error that applies to new work in the current state (cv held)."""
        if self._error is not None:
            return self._error
        if self._state != "RUNNING":
            return WalClosed()
        return None

    def _has_space(self, size: int) -> bool:
        """Return True if an item of `size` bytes fits the bounded queue (cv held)."""
        if not self._queue:
            return True
        return (
            len(self._queue) < self._cfg.queue_max_items
            and self._queued_bytes + size <= self._cfg.queue_max_bytes
        )

    def _enqueue_rotate_locked(self, done: _Done | None) -> None:
        """Allocate a seal seq and queue a rotation; projected segment restarts (cv held)."""
        seal_seq = self._next_seq
        self._next_seq += 1
        self._queue.append(_Rotate(seal_seq=seal_seq, done=done))
        self._proj_bytes = SEGMENT_HEADER_LEN
        self._proj_records = 0
        _log.info("rotation queued: seal seq %d", seal_seq)

    def _set_state_locked(self, state: str) -> None:
        """Change writer state and log it (cv held)."""
        _log.info("WAL writer state %s -> %s", self._state, state)
        self._state = state

    # -- writer thread ----------------------------------------------------------------------

    def _run(self) -> None:
        """Thread body: group-commit loop; any failure parks the writer in FAILED."""
        try:
            while True:
                batch = self._take_batch()
                outcome = self._process(batch)
                if outcome.is_err:
                    self._enter_failed(outcome.danger_err)
                    return
                if outcome.danger_ok:
                    return
        except Exception as exc:  # noqa: BLE001 - thread boundary: a bug must not vanish
            _log.exception("WAL writer thread crashed")
            self._enter_failed(WalInternal(detail=repr(exc)))

    def _take_batch(self) -> list[_Item]:
        """Block for the first item, then drain up to the batch limits without blocking."""
        batch: list[_Item] = []
        size = 0
        records = 0
        with self._cv:
            while not self._queue:
                self._cv.wait()
            while self._queue and records < self._cfg.batch_max_records:
                nxt = self._queue[0]
                cost = _item_size(nxt)
                if batch and size + cost > self._cfg.batch_max_bytes:
                    break
                self._queue.popleft()
                self._queued_bytes -= cost
                batch.append(nxt)
                size += cost
                records += isinstance(nxt, Record)
            self._cv.notify_all()
        return batch

    def _process(self, batch: list[_Item]) -> Result[bool, WalError]:
        """Handle a batch in order; Ok(True) means a Stop was honored and the thread ends."""
        pending: list[Record] = []
        for index, item in enumerate(batch):
            if isinstance(item, Record):
                pending.append(item)
                continue
            flushed = self._flush(pending)
            if flushed.is_err:
                self._stash(pending, batch[index:])
                return Err(flushed.danger_err)
            pending = []
            if isinstance(item, _Rotate):
                rotated = self._rotate(item.seal_seq)
                if item.done is not None:
                    item.done.set(rotated)
                if rotated.is_err:
                    self._stash([], batch[index + 1 :])
                    return Err(rotated.danger_err)
                continue
            self._finish(item)
            return Ok(True)
        flushed = self._flush(pending)
        if flushed.is_err:
            self._stash(pending, [])
            return Err(flushed.danger_err)
        return Ok(False)

    def _stash(self, pending: list[Record], rest: list[_Item]) -> None:
        """Keep undurable records of a failed batch (in order) for retry or spill."""
        with self._cv:
            self._undurable = pending + [i for i in rest if isinstance(i, Record)]
        for item in rest:
            done = getattr(item, "done", None)
            if isinstance(done, _Done):
                self._pending_dones.append(done)

    def _flush(self, frames: list[Record]) -> Result[None, WalError]:
        """Write `frames` as one buffer, fsync, then publish durable_seq (one group commit)."""
        if not frames:
            return Ok(None)
        hit = _hit("wal.encode.before")
        if hit.is_err:
            return hit
        encoded = [encode_frame(f.type, f.seq, f.wall_ns, f.flags, f.payload) for f in frames]
        buf = b"".join(encoded)
        try:
            cut = len(buf) // 2
            _write_all(self._fd, buf[:cut])
            partial = _hit("wal.write.partial")
            if partial.is_err:
                return partial
            _write_all(self._fd, buf[cut:])
        except OSError as exc:
            _log.error("write of %d records failed: %s", len(frames), exc)
            return Err(WalFailed(reason=f"write: {exc}", errno=exc.errno))
        self._seg_hash.update(buf)
        self._seg_bytes += len(buf)
        self._seg_records += len(frames)
        for step in (_hit("wal.write.after"), self._fsync()):
            if step.is_err:
                return step
        last = frames[-1].seq
        with self._cv:
            self._durable_seq = last
            self._batches += 1
            self._last_batch = len(frames)
            self._cv.notify_all()
        _log.debug("durable_seq -> %d (%d records, %d bytes)", last, len(frames), len(buf))
        return _hit("wal.publish.after")

    def _fsync(self) -> Result[None, WalError]:
        """Flush the active segment with failpoints and latency accounting."""
        before = _hit("wal.fsync.before")
        if before.is_err:
            return before
        start = time.perf_counter()
        synced = durable.fsync_file(self._fd)
        ms = (time.perf_counter() - start) * 1000.0
        if synced.is_err:
            return Err(_durable_err(synced.danger_err))
        with self._cv:
            self._last_fsync_ms = ms
            self._max_fsync_ms = max(self._max_fsync_ms, ms)
            observer = self._fsync_observer
        if observer is not None:
            observer(ms)
        if ms > SLOW_FSYNC_MS:
            _log.warning("slow fsync: %.1f ms", ms)
        return _hit("wal.fsync.after")

    @propagate
    def _rotate(self, seal_seq: int) -> Result[None, WalError]:
        """Rotation steps of section 4.2: seal+fsync, create+header+fsync, dir fsync, switch."""
        payload = encode_seal(
            self._seg_records, self._seg_first_seq, seal_seq - 1, self._seg_hash.digest()
        )
        frame = encode_frame(int(RecordType.SEAL), seal_seq, time.time_ns(), 0, payload)
        try:
            _write_all(self._fd, frame)
        except OSError as exc:
            _log.error("seal write failed: %s", exc)
            return Err(WalFailed(reason=f"seal write: {exc}", errno=exc.errno))
        _hit("wal.rotate.after_seal_write").unwrap()
        self._fsync().unwrap()
        _hit("wal.rotate.after_seal_fsync").unwrap()
        next_no = self._seg_no + 1
        path = self._dir / segment_name(next_no)
        new_fd = create_exclusive(path).map_err(_durable_err).unwrap()
        _hit("wal.rotate.after_create").unwrap()
        header = encode_segment_header(next_no, seal_seq + 1, self._uuid)
        try:
            _write_all(new_fd, header)
            _hit("wal.rotate.after_header").unwrap()
            durable.fsync_file(new_fd).map_err(_durable_err).unwrap()
            _hit("wal.rotate.after_header_fsync").unwrap()
            fsync_dir(self._dir).map_err(_durable_err).unwrap()
            _hit("wal.rotate.after_dir_fsync").unwrap()
        except OSError as exc:
            durable_close(new_fd)
            return Err(WalFailed(reason=f"new segment header: {exc}", errno=exc.errno))
        old_fd = self._fd
        self._fd = new_fd
        durable_close(old_fd)
        self._seg_no = next_no
        self._seg_first_seq = seal_seq + 1
        self._seg_records = 0
        self._seg_bytes = SEGMENT_HEADER_LEN
        self._seg_hash = hashlib.sha256()
        self._seg_hash.update(header)
        with self._cv:
            self._rotations += 1
        _log.info("rotated to %s (first_seq %d)", path.name, seal_seq + 1)
        return Ok(None)

    def _finish(self, stop: _Stop) -> None:
        """Close the active segment (left unsealed) and publish CLOSED."""
        durable_close(self._fd)
        with self._cv:
            self._set_state_locked("CLOSED")
            self._cv.notify_all()
        stop.done.set(Ok(None))

    def _enter_failed(self, error: WalError) -> None:
        """Park the writer in FAILED, keep the queue, fail every waiter (section 6.5)."""
        _log.error("WAL writer FAILED: %s", error)
        with self._cv:
            self._error = error
            self._set_state_locked("FAILED")
            dones = [d for i in self._queue if isinstance(d := getattr(i, "done", None), _Done)]
            observer = self._failure_observer
            self._cv.notify_all()
        for done in dones + self._pending_dones:
            done.set(Err(error))
        self._pending_dones = []
        if observer is not None:
            try:
                observer(error)
            except Exception:  # noqa: BLE001 - a listener bug must not hide the failure
                _log.exception("WAL failure observer raised")


def durable_close(fd: int) -> None:
    """Close `fd`, logging (not raising) on failure; the fd is always released."""
    import os  # noqa: PLC0415

    try:
        os.close(fd)
    except OSError as exc:
        _log.error("close(fd=%d) failed: %s", fd, exc)


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte of `data`, handling short writes; raises OSError on failure."""
    import os  # noqa: PLC0415

    view = memoryview(data)
    while view:
        failpoint("durable.write")
        written = os.write(fd, view)
        view = view[written:]


# ---- reader ------------------------------------------------------------------------------


class TornTail(BaseModel):
    """Unverified bytes at the end of the last segment; left in place, never truncated."""

    model_config = ConfigDict(frozen=True)
    segment: int
    offset: int
    length: int
    sha256: str
    reason: str


class SegmentInfo(BaseModel):
    """Verification summary of one segment."""

    model_config = ConfigDict(frozen=True)
    segment_no: int
    size: int
    first_seq: int
    last_seq: int | None
    record_count: int
    sealed: bool
    verified_bytes: int


class ScanReport(BaseModel):
    """Result of a read-only recovery scan: verified prefix, hash and torn tail (section 5)."""

    model_config = ConfigDict(frozen=True)
    wal_dir: Path
    session_uuid: uuid.UUID
    segments: tuple[SegmentInfo, ...]
    record_count: int
    first_seq: int | None
    last_seq: int | None
    prefix_hash: str
    tail: TornTail | None


class _Walker:
    """Single-pass verifier shared by `scan` and `records`; never writes anything."""

    def __init__(self, wal_dir: Path) -> None:
        """Remember the directory; state is filled by `run`."""
        self.dir = wal_dir
        self.error: WalError | None = None
        self.tail: TornTail | None = None
        self.segments: list[SegmentInfo] = []
        self.count = 0
        self.first_seq: int | None = None
        self.last_seq: int | None = None
        self.phash = new_prefix_hash()
        self.uuid: uuid.UUID | None = None

    def report(self) -> ScanReport:
        """Build the ScanReport for what has been verified so far."""
        return ScanReport(
            wal_dir=self.dir,
            session_uuid=self.uuid or uuid.UUID(int=0),
            segments=tuple(self.segments),
            record_count=self.count,
            first_seq=self.first_seq,
            last_seq=self.last_seq,
            prefix_hash=self.phash.hexdigest(),
            tail=self.tail,
        )

    def _corrupt(self, segment: int, offset: int, reason: str) -> None:
        """Record a corruption error carrying the verified prefix summary."""
        _log.error("WAL corrupt: seg %d offset %d: %s", segment, offset, reason)
        self.error = WalCorrupt(
            segment=segment,
            offset=offset,
            reason=reason,
            prefix_last_seq=self.last_seq or 0,
            prefix_records=self.count,
        )

    def run(self) -> Iterator[Record]:
        """Yield verified data records in order; set `error` or `tail` where verification stops."""
        files: list[tuple[int, Path]] = []
        for p in sorted(self.dir.iterdir()):
            m = _SEG_NAME.match(p.name)
            if m:
                files.append((int(m.group(1)), p))
        if not files:
            self.error = WalSegmentHeaderInvalid(segment=None, reason="no segment files")
            return
        for want, (no, _p) in enumerate(files, start=1):
            if no != want:
                self._corrupt(want, 0, f"segment file gap: {segment_name(want)} missing")
                return
        expected_seq = 0
        prev_sealed = True
        for idx, (no, path) in enumerate(files):
            is_last = idx == len(files) - 1
            with path.open("rb") as f:
                size = path.stat().st_size
                head = f.read(SEGMENT_HEADER_LEN)
                hdr = decode_segment_header(head, no)
                if hdr.is_err:
                    err = hdr.danger_err
                    if is_last and idx > 0 and prev_sealed and size <= SEGMENT_HEADER_LEN:
                        self._set_tail(f, no, 0, size, "partial segment header (crash in rotation)")
                        return
                    self.error = err
                    return
                h = hdr.danger_ok
                if h.segment_no != no:
                    self._corrupt(no, 0, f"header segment_no {h.segment_no} != file name")
                    return
                if self.uuid is not None and h.session_uuid != self.uuid:
                    self._corrupt(no, 0, "session uuid differs from earlier segment")
                    return
                if idx > 0 and h.first_seq != expected_seq:
                    self._corrupt(no, 0, f"first_seq {h.first_seq} != expected {expected_seq}")
                    return
                self.uuid = h.session_uuid
                expected_seq = h.first_seq
                state = _SegState(no=no, size=size, first_seq=h.first_seq)
                shash = hashlib.sha256(head)
                yield from self._walk_segment(f, state, shash, is_last, expected_seq)
                expected_seq = state.expected
                self.segments.append(state.info())
                if self.error is not None or self.tail is not None:
                    return
                prev_sealed = state.sealed
                if not state.sealed and not is_last:
                    self._corrupt(no, state.pos, "unsealed segment followed by another segment")
                    return

    def _walk_segment(
        self, f: BinaryIO, st: _SegState, shash: hashlib._Hash, is_last: bool, expected: int
    ) -> Iterator[Record]:
        """Verify records of one open segment, updating `st` and walker totals."""
        st.expected = expected
        pos = SEGMENT_HEADER_LEN
        while pos < st.size:
            st.pos = pos
            remaining = st.size - pos
            bad: str | None = None
            header = f.read(FRAME_HEADER_LEN) if remaining >= FRAME_HEADER_LEN else b""
            payload = b""
            rec: Record | None = None
            if remaining < FRAME_HEADER_LEN:
                bad = "partial header"
            else:
                parsed = parse_header(header, pos)
                if parsed.is_err:
                    bad = parsed.danger_err.reason
                else:
                    length = parsed.danger_ok[4]
                    if pos + FRAME_HEADER_LEN + length > st.size:
                        bad = "partial payload"
                    else:
                        payload = f.read(length)
                        decoded = decode_payload_check(header, payload, pos)
                        if decoded.is_err:
                            bad = decoded.danger_err.reason
                        else:
                            rec = decoded.danger_ok
            if rec is None:
                self._classify_bad(f, st, pos, bad or "invalid frame", is_last)
                return
            if rec.seq != st.expected:
                self._corrupt(
                    st.no, pos, f"seq gap or repeat: expected {st.expected} got {rec.seq}"
                )
                return
            end = pos + FRAME_HEADER_LEN + len(payload)
            if rec.type == RecordType.SEAL:
                if not self._check_seal(st, rec, shash, end):
                    return
                st.sealed = True
                st.expected = rec.seq + 1
                st.pos = end
                _log.debug("segment %d sealed ok", st.no)
                return
            shash.update(header)
            shash.update(payload)
            st.count += 1
            st.last_seq = rec.seq
            st.expected = rec.seq + 1
            self.count += 1
            if self.first_seq is None:
                self.first_seq = rec.seq
            self.last_seq = rec.seq
            prefix_hash_update(self.phash, rec)
            pos = end
            st.pos = pos
            yield rec
        st.pos = pos

    def _check_seal(self, st: _SegState, rec: Record, shash: hashlib._Hash, end: int) -> bool:
        """Verify a SEAL record's counts, hash and position; record corruption on failure."""
        seal = decode_seal(rec.payload)
        if seal.is_err:
            self._corrupt(st.no, st.pos, seal.danger_err.reason)
            return False
        s = seal.danger_ok
        if (
            s.record_count != st.count
            or s.first_seq != st.first_seq
            or s.last_seq != rec.seq - 1
            or s.sha256 != shash.digest()
        ):
            self._corrupt(st.no, st.pos, "seal counts or SHA-256 do not match segment contents")
            return False
        if end != st.size:
            self._corrupt(st.no, end, "bytes after seal")
            return False
        return True

    def _classify_bad(
        self, f: BinaryIO, st: _SegState, pos: int, reason: str, is_last: bool
    ) -> None:
        """Decide torn tail versus corruption for a bad frame at `pos` (section 5.2)."""
        if not is_last:
            self._corrupt(st.no, pos, f"{reason} in a non-final segment")
            return
        if _valid_frame_after(f, st.size, pos + 1, st.expected):
            self._corrupt(st.no, pos, f"{reason}; valid records follow")
            return
        self._set_tail(f, st.no, pos, st.size - pos, reason)

    def _set_tail(self, f: BinaryIO, segment: int, offset: int, length: int, reason: str) -> None:
        """Record the torn tail with the SHA-256 of its bytes; nothing is modified."""
        f.seek(offset)
        h = hashlib.sha256()
        left = length
        while left > 0:
            chunk = f.read(min(_SCAN_CHUNK, left))
            if not chunk:
                break
            h.update(chunk)
            left -= len(chunk)
        self.tail = TornTail(
            segment=segment, offset=offset, length=length, sha256=h.hexdigest(), reason=reason
        )
        _log.warning(
            "WAL torn tail: seg %d offset %d length %d sha256 %s (%s); bytes left in place",
            segment,
            offset,
            length,
            self.tail.sha256,
            reason,
        )


@dataclass
class _SegState:
    """Mutable per-segment verification state."""

    no: int
    size: int
    first_seq: int
    pos: int = SEGMENT_HEADER_LEN
    count: int = 0
    last_seq: int | None = None
    expected: int = 0
    sealed: bool = False

    def info(self) -> SegmentInfo:
        """Freeze the state into a SegmentInfo."""
        return SegmentInfo(
            segment_no=self.no,
            size=self.size,
            first_seq=self.first_seq,
            last_seq=self.last_seq,
            record_count=self.count,
            sealed=self.sealed,
            verified_bytes=self.pos,
        )


def _valid_frame_after(f: BinaryIO, size: int, start: int, expected_seq: int) -> bool:
    """Return True if any CRC-valid frame with seq >= expected_seq starts at or after `start`."""
    pos = start
    while pos < size:
        f.seek(pos)
        chunk = f.read(_SCAN_CHUNK)
        if not chunk:
            return False
        idx = chunk.find(FRAME_MAGIC)
        while idx != -1:
            cand = pos + idx
            if _frame_ok_at(f, size, cand, expected_seq):
                return True
            idx = chunk.find(FRAME_MAGIC, idx + 1)
        if pos + len(chunk) >= size:
            return False
        pos += len(chunk) - (len(FRAME_MAGIC) - 1)
    return False


def _frame_ok_at(f: BinaryIO, size: int, cand: int, expected_seq: int) -> bool:
    """Return True if a valid frame with seq >= expected_seq starts exactly at `cand`."""
    if cand + FRAME_HEADER_LEN > size:
        return False
    f.seek(cand)
    header = f.read(FRAME_HEADER_LEN)
    parsed = parse_header(header, cand)
    if parsed.is_err:
        return False
    length = parsed.danger_ok[4]
    if cand + FRAME_HEADER_LEN + length > size:
        return False
    decoded = decode_payload_check(header, f.read(length), cand)
    return decoded.is_ok and decoded.danger_ok.seq >= expected_seq


class WalReader:
    """Read-only WAL access: verified iteration and recovery scan; never modifies files."""

    def __init__(self, wal_dir: Path) -> None:
        """Bind the reader to `wal_dir` (the `wal/` directory holding `seg-NNNNNN.wal`)."""
        self._dir = wal_dir
        self._report: ScanReport | None = None

    @property
    def report(self) -> ScanReport | None:
        """ScanReport of the last completed iteration (None until `records` is exhausted)."""
        return self._report

    @staticmethod
    def scan(wal_dir: Path) -> Result[ScanReport, WalError]:
        """Verify the whole WAL; Err on corruption, Ok with `tail` set when a torn tail exists."""
        walker = _Walker(wal_dir)
        for _ in walker.run():
            pass
        if walker.error is not None:
            return Err(walker.error)
        report = walker.report()
        _log.info(
            "WAL scan %s: %d records last_seq=%s tail=%s",
            wal_dir,
            report.record_count,
            report.last_seq,
            report.tail is not None,
        )
        return Ok(report)

    def records(self, from_seq: Seq = 1) -> Iterator[Result[Record, WalError]]:
        """Yield verified data records with seq >= from_seq; a final Err ends a corrupt log."""
        walker = _Walker(self._dir)
        for rec in walker.run():
            if rec.seq >= from_seq:
                yield Ok(rec)
        self._report = walker.report()
        if walker.error is not None:
            yield Err(walker.error)
