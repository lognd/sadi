# Data-safety design: WAL, sessions, snapshots, durability, recovery

Status: current

Owner ticket: DS1 ~CKTER59 (design document). Implementing tickets: DS2 ~JA5DMTN (durable primitives), DS3 ~4668M06 (WAL),
DS4 ~GCJAR1J (sessions), DS5 ~K6BT3MG (events and snapshots), DS6 ~HAH4MTB
(crash tests), DS7 ~36JQFXT (exports), DS8 ~3F2W55E (writer thread), B3
~60ZNFTD (pipeline gate), CC1 ~DK06Q2F ([concurrency model](concurrency.md)). Each implements
the section that names it, exactly as written; a deviation is a change to
this file in the same ticket, not a silent divergence.

The user's requirement, verbatim:

> AT NO POINT SHOULD WE BE ABLE TO LOSE ANY DATA. EVERYTHING MUST BE ATOMIC
> AND RECOVERABLE AND NOT AUTOMATICALLY OVERWRITTEN.

Context: a conventional DAQ front end holds every row in memory and writes the
CSV only at Stop; an abort, a crash or a cancelled save dialog loses the run
(docs/domain.md section 8). This design makes the opposite choice at
every layer: the raw byte stream is durable before it is displayed, nothing
is ever edited in place, and everything the user sees is derived from the
durable record.

## 0. Contents

1. Invariants (the contract every ticket tests against)
2. Decisions and rationale (language, checksum, what is stored)
3. Record framing and type registry
4. Segment files, rotation, sealing
5. Recovery: torn tail, corruption, chain verification
6. Durability contract: fsync policy, group commit, durable_seq, the display
   gate, disk-full and I/O errors
7. Writer thread: queue, backpressure, metrics, shutdown
8. Session directories: naming, exclusive creation, manifest, lock, resume
9. Snapshots (derived, atomic) and exports (derived, provenance)
10. Per-OS durability table
11. Failpoints (fault-injection hooks)
12. Crash-recovery test plan
13. Failure modes table
14. Schema versioning and compatibility policy
15. Module map, public API signatures and error taxonomy
16. Open points and tickets to split off

## 1. Invariants

Every invariant has a short id. Tests in DS3, DS5, DS6 and B3 cite the id in
their test names and `frob:tests` bindings. "Record" means one framed WAL
record (section 3). "Acknowledged" means `durable_seq >= record.seq` was
published to a consumer (section 6).

| Id | Name | Statement |
|---|---|---|
| I1 | Prefix property | After any crash, the recovered record sequence of a WAL version is exactly a prefix `1..N` of what was appended, in order, with no gaps and no reordering. |
| I2 | No acknowledged loss | Every record that was acknowledged before the crash is present after recovery. (A record appended but not yet acknowledged may be lost; it was never shown as saved.) |
| I3 | No accepted corruption | No record whose bytes differ from what the writer produced is ever returned by a reader. Detection is by CRC-32C plus structural checks; the reader stops or errors, it never guesses. |
| I4 | No overwrite | No byte of an existing file under a session directory is ever modified or truncated by SADI, and no existing file or directory is ever replaced except the derived files listed in section 9 (manifest cache, snapshot, export) via atomic rename, and even those are replaced only when the replacement is a superset of the information. Session directories are never deleted or reused. |
| I5 | Snapshot old-or-new | At every instant, a snapshot or export path either does not exist, or contains the complete old content, or contains the complete new content. Never a torn file at its final path. |
| I6 | Durable before display | The display and analysis pipelines only receive a raw block after `durable_seq` covers its record (section 6.4). Nothing a user sees as data is undurable. |
| I7 | Derived is regenerable | Deleting every snapshot and export, and the manifest cache, loses nothing: all are rebuilt from the WAL chain (section 9). |
| I8 | Single writer | At most one process holds a session version writable; readers never mutate a session (not even to "repair" it). |
| I9 | Loud failure | Any durability failure (write error, fsync error, disk full, lock conflict, corruption) stops acquisition with a typed error surfaced to the UI and the log. Silent skipping, silent retry-until-success or silent downgrade of durability are forbidden. |
| I10 | Raw is primary | Analysis state (points, fits, edits) is a deterministic function of the WAL chain. Re-running replay on the same chain yields byte-identical state (DS5 property test). |

## 2. Decisions and rationale

### 2.1 Language: Python, `python/sadi/store/`

Decision: the whole store (durable primitives, WAL, sessions, events,
snapshots, exports, writer thread) is Python, package `sadi.store` under
`python/sadi/store/` (the paths in the DS2-DS8 ticket scopes).

Rationale:

- Throughput is trivial. The device emits 612 kB/s (1000 packets/s,
  docs/protocol.md section 3). The writer stores raw blocks of 10-50 packets
  per record (section 3.4), i.e. 20-100 records/s and 20-100 CRC
  computations over ~6-30 kB each. A C-implemented CRC-32C runs at GB/s;
  `os.write` plus one `fsync` per batch dominates and is OS-bound either way.
- The session, event and snapshot logic is pydantic-model heavy and is
  consumed by the FastAPI layer; one implementation in one language avoids
  two WAL codecs and a PyO3 boundary on the hottest safety path.
- Failpoints (section 11) and the crash harness (section 12) are far simpler
  to drive in the same interpreter.
- Rejected: Rust WAL in `sadi-proto`. It would add a second owner of the
  on-disk format and force every record type (points, edits, notes) through
  PyO3. Revisit only if measured p99 append latency (DS3 acceptance 3)
  exceeds the budget in section 6.6.

Dependency note: CRC-32C is not in the standard library. DS3 adds the
`crc32c` package (C extension with SSE4.2/ARMv8 acceleration, wheels for all
three OS, pure-Python fallback inside the package). That requires a lease
widen onto `python/pyproject.toml` (owned by P1) in DS3. The checksum
algorithm is identified in the segment header (section 4.1) so the choice is
explicit on disk.

### 2.2 What is stored: raw packets, not decoded samples

The WAL stores the 612-byte device packets exactly as received, plus every
byte the resync decoder discarded. Decoding (ADC scaling mode, encoder
combine, channel count) is applied on read. Reasons: the protocol is
unverified (docs/hardware-verification.md rows 2, 3, 4); a decode bug or a
changed scaling constant must never cost a run. Settings needed to decode
(ADC range codes, which the device never echoes) are recorded as a
`SETTINGS` record before the first `RAW_BLOCK`.

Implementation: `LiveAcquisition.on_session_open` calls
`AcquisitionPipeline.record_settings` (scopes `device`: ADC mode, full-scale
volts, code bits, rate, kind, firmware; `acquisition`: decimation, packet
length) and waits for them to be durable before the device starts. Every
version, including a resume, writes its own. Sessions recorded before this
have none; they still open and replay, and Doctor WAL-040 keeps flagging them
(their WAL is never rewritten).

### 2.3 Nothing is edited in place; recovery never writes to the old data

Points, window edits, exclusions, settings changes, notes and markers are
WAL records. "Current state" is replay. Recovery after a crash never
truncates, rewrites or deletes anything (section 5): the reader ignores a
torn tail logically, and a resumed session is a new version directory
whose first record documents what was found. This is stricter than the
usual "truncate the torn tail" rule and is chosen because the user's
requirement forbids destructive repair.

The server derives per-action state with `IncrementalReplay`, which reads
only newly appended frames and falls back to a full verified replay on any
anomaly; it is always equal to a full replay (see store/incremental-replay.md).

### 2.4 Checksum: CRC-32C (Castagnoli), per record, header plus payload

CRC-32C over the header (with the crc field zero) and the payload detects
torn writes, bit flips and misframing. It is not a cryptographic
integrity guarantee; segment seals (section 4.3) add SHA-256 over the whole
segment for archival verification.

## 3. Record framing and type registry

### 3.1 Frame

All integers little-endian. No alignment padding. A record is:

```
offset  size  field        notes
0       4     magic        bytes 53 41 44 52  ("SADR")
4       1     version      frame version, currently 1
5       1     type         record type code (section 3.3)
6       2     flags        bit 0: payload is JSON (UTF-8); bit 1: payload is
                           zlib-compressed (reserved, writer never sets it
                           in v1); other bits must be 0
8       8     seq          uint64, first record of a version = 1, +1 per record,
                           continues across versions of a family (section 8.5)
16      8     wall_ns      int64 Unix time in ns (UTC) when the record was
                           enqueued (informational; ordering is by seq)
24      4     length       uint32 payload length in bytes; 0 <= length <= 2^24
28      4     crc32c       CRC-32C over bytes 0..27 of the header (with this
                           field as 00 00 00 00) followed by the payload
32      n     payload
```

Header size is 32 bytes; constant `FRAME_HEADER_LEN = 32`. Maximum payload
`MAX_PAYLOAD = 16 MiB`; a length above it is a framing error (section 5).

The CRC covers the header so that a corrupted `length` or `seq` is caught
before the payload is trusted; the reader must check `magic`, `version`,
`flags`, `length <= MAX_PAYLOAD` and `length <= bytes remaining` before
computing the CRC, and must treat any of those failing exactly like a CRC
failure for the purpose of section 5.

### 3.2 Record encoding rules

- `RAW_BLOCK`, `RAW_JUNK` and `SEAL` payloads are binary (flags bit 0 = 0)
  with the layouts below.
- Every other payload is a UTF-8 JSON object produced by
  `pydantic.BaseModel.model_dump_json()` (flags bit 0 = 1) and contains a
  top-level integer field `"v"` (payload schema version, starts at 1).
- A record type's payload model lives in `sadi/store/records.py` (DS3) as a
  pydantic model with `model_config = ConfigDict(extra="allow")` so that
  newer fields survive a round trip through an older reader.

### 3.3 Type registry

Type codes are one byte. Codes 0x00 and 0x80-0xFF are reserved and invalid.
A reader that meets an unknown code in 0x01-0x7F with a valid CRC returns an
`UnknownRecord(type, seq, payload)`; it never fails on it (section 14).

| Code | Name | Payload | Written by | Purpose |
|---|---|---|---|---|
| 0x01 | SESSION_START | JSON `SessionStartV1` | DS4 | First record of every version: session identity, parent link, code version, environment, result of opening the parent (torn tail, if any). |
| 0x02 | RAW_BLOCK | binary (3.4) | B3 via DS8 | Consecutive device packets as received. |
| 0x03 | RAW_JUNK | binary (3.5) | B3 via DS8 | Bytes the resync decoder discarded between valid packets, so no byte from the device is lost. |
| 0x04 | MARKER | JSON `MarkerV1` | pipeline, UI | Timeline events: phase change, load applied, tare start/stop, cal capture start/stop, settle detected, settle forced-early, acquisition start/stop (with reason), user bookmark. Fields: `kind`, `label`, `raw_seq` (seq of the RAW_BLOCK current at the marker), `data` (dict). |
| 0x05 | POINT | JSON `PointV1` | DS5 | A captured point: `point_id` (uuid4), `phase`, `window` (first/last raw seq and sample offsets), `t_since_load_s`, `drift_rate`, `settled` or `forced_early`, inputs sampled at capture (load N, L0, etc. as a dict), `computed` (values as computed at capture time, for audit only; replay recomputes). |
| 0x06 | EDIT | JSON `EditV1` | DS5 | Edit of a point or of analysis settings: `target` (point_id or "analysis"), `op` (`exclude`, `include`, `set_window`, `override_input`, `set_fit_window`, `undo`, `redo`), `args` (dict), `edit_id` (uuid4), `supersedes` (edit_id or null). Edits are append-only; undo is itself an EDIT. |
| 0x07 | SETTINGS | JSON `SettingsV1` | B3, UI | A settings change: `scope` (`device`, `acquisition`, `analysis`, `ui`), `key`, `value`, `previous`. The ADC range codes and sample rate MUST be written before the first RAW_BLOCK of a version. |
| 0x08 | NOTE | JSON `NoteV1` | UI | Free-text operator note: `text`, `author`, `raw_seq`. |
| 0x09 | DEVICE_EVENT | JSON `DeviceEventV1` | B3 | Connect, disconnect, reconnect, version packet seen, stop-ack seen, saturation purge, resync, transport error. Fields: `kind`, `detail` (dict). |
| 0x0A | SNAPSHOT_REF | JSON `SnapshotRefV1` | DS5 | A snapshot was committed: `path` (relative), `covers_seq`, `prefix_hash`, `sha256`. Written after the rename succeeds. |
| 0x0B | EXPORT_REF | JSON `ExportRefV1` | DS7 | An export was committed: `path`, `kind`, `covers_seq`, `sha256`, `snapshot_path`. |
| 0x0C | SESSION_CLOSE | JSON `SessionCloseV1` | DS4 | Clean close: `last_raw_seq`, `reason` (`user`, `stop`, `error`), `error` (typed error dict or null). Absence means the version was not closed cleanly. |
| 0x7E | SEAL | binary (4.3) | DS3 | Last record of a rotated segment. |
| 0x7F | PAD | empty | DS3 | Reserved; writer never emits it in v1. Readers accept it (CRC must still be valid). |

### 3.4 RAW_BLOCK payload (binary, layout version 1)

```
offset  size  field
0       2     layout        uint16 = 1
2       2     packet_len    uint16, 612 for v1.003 firmware
4       4     count         uint32 number of packets, 1 <= count <= 1000
8       8     mono_ns       uint64 host monotonic clock at receipt of packet 0
16      8     wall_ns       int64 host wall clock (UTC ns) at receipt of packet 0
24      4     first_msgcount uint32 msgCount of packet 0 (0xFFFFFFFF if packet 0
                            is not a data packet)
28      4     flags         bit 0: a RAW_JUNK record precedes this block (bytes
                            were discarded before packet 0); bit 1: block
                            contains at least one non-data packet (type 4 or 2)
32      count*packet_len   the packets, byte-exact as received
```

A block holds the packets delivered in one acquisition batch (R8 bounded
channel), capped at 1000 packets (1 s). Packets are never split across
blocks. `count` and `packet_len` must satisfy `32 + count*packet_len ==
length` or the record is a framing error.

### 3.5 RAW_JUNK payload (binary)

```
offset  size  field
0       2     layout     uint16 = 1
2       2     reserved   0
4       8     mono_ns    uint64 host monotonic clock when the discard was detected
12      4     reason     uint32: 1 resync (no header), 2 bad tail, 3 saturation
                         purge (bytes unknown, length 0), 4 truncated by Stop
16      n     the discarded bytes
```

### 3.6 JSON payload base fields

Every JSON payload has `"v": 1` and may carry `"note": str`. Models are
frozen pydantic models; the writer serialises with `model_dump_json()`
(no indentation, UTF-8). Field names are snake_case. Timestamps inside
JSON are RFC 3339 UTC strings with `Z`; the frame's `wall_ns` is
authoritative for ordering diagnostics.

## 4. Segment files, rotation, sealing

### 4.1 Segment file

Path: `<session-dir>/wal/seg-<NNNNNN>.wal`, `NNNNNN` zero-padded decimal
starting at `000001` within a version. Created with exclusive create
(section 10) and opened append-only; the writer holds the fd for the
segment's life and never seeks.

Segment header, 64 bytes, written and fsynced before any record:

```
offset  size  field
0       8     magic           53 41 44 49 57 41 4C 00  ("SADIWAL\0")
8       2     format_version  uint16 = 1 (on-disk format: header + frame rules)
10      1     checksum_algo   uint8: 1 = CRC-32C (Castagnoli)
11      1     reserved        0
12      4     segment_no      uint32, matches the file name
16      8     first_seq       uint64 seq of the first record this segment may hold
24      16    session_uuid    the version's uuid4 (also in the manifest)
40      8     created_ns      int64 Unix ns
48      12    reserved        zeros
60      4     header_crc32c   CRC-32C over bytes 0..59
```

Records follow at offset 64, back to back.

### 4.2 Rotation

Rotate when the current segment would exceed `SEGMENT_MAX_BYTES = 256 MiB`
(about 7 minutes of raw at 612 kB/s; rotation keeps per-file verification
and torn-tail scans bounded) or at an explicit `rotate()` request. Order of
operations, each step a failpoint (section 11):

1. Append the `SEAL` record to segment N (section 4.3); write; fsync(file).
2. Create `seg-N+1.wal` exclusively; write the 64-byte header; fsync(file).
3. fsync(dir `wal/`) (ctypes flush on Windows, section 10).
4. Switch the writer's active fd to N+1; close N.

`durable_seq` does not advance during rotation (no records are written in
steps 2-4). Recovery rules for crashes between steps are in section 5.3.

### 4.3 SEAL record

Type 0x7E, binary payload:

```
offset  size  field
0       2     layout        uint16 = 1
2       2     reserved      0
4       4     record_count  uint32 records in this segment excluding the seal
8       8     first_seq     uint64
16      8     last_seq      uint64 (seq of the record before the seal)
24      32    sha256        SHA-256 over every byte of the segment file from
                            offset 0 up to the first byte of the seal record
```

The seal takes the next seq like any record; the reader treats it as a
structural record and does not return it as data. A segment whose last
record is a valid seal is "sealed". Sealed segments can be archived and
verified byte-for-byte without a reader.

## 5. Recovery

Recovery is a pure read: it opens files read-only and writes nothing
(I4, I8). `WalReader.scan(version_dir) -> Result[ScanReport, WalError]`
returns the verified prefix, its last seq, the prefix hash (section 9.2) and
a `tail` description. A writable resume (section 8.6) stores the
`ScanReport` of the parent in its `SESSION_START` record.

### 5.1 Reading a segment

For each segment in file-name order:

1. Read 64 bytes; verify magic, format_version in the supported set,
   checksum_algo known, header CRC, `segment_no` equals the file name,
   `session_uuid` equals the manifest / previous segments. Any mismatch:
   `SegmentHeaderInvalid` (section 5.4 decides torn vs corrupt).
2. Loop: read 32 bytes at `pos`. If fewer than 32 remain, stop with
   `tail = Partial(pos, remaining_bytes)`. Verify magic, version, flags,
   length bounds, `seq == expected_seq`. Read payload; verify CRC. On any
   failure stop with `tail = Invalid(pos, reason)`.
3. On a valid `SEAL`: verify `record_count`, `first_seq`, `last_seq` and the
   SHA-256; mismatch is `Corrupt`. Verify the seal is the last bytes in the
   file (trailing bytes after a seal are `Corrupt`). Mark segment sealed.

### 5.2 Torn tail versus corruption

The prefix ends at `pos` (the start of the first bad record). Classify:

- Torn tail (expected after a crash or power loss): the segment is the last
  segment of the version, is unsealed, and no valid record exists after
  `pos`. "No valid record after pos" is decided by scanning forward from
  `pos + 1` for a frame whose magic, version, structural fields and CRC
  are valid and whose `seq` is `>= expected_seq`. If none is found, it is
  a torn tail. The bytes from `pos` to EOF are reported as
  `tail = Torn(pos, len)` and are left in place.
- Corruption: any bad record in a sealed segment; any bad record in a
  non-last segment; any bad record followed later in the file by a valid
  record; a seal whose counts or hash mismatch; a `seq` gap or repeat.
  Result is `Err(WalError.Corrupt(segment, pos, reason))`.

Consequences:

- A torn tail is normal. Read-only open returns the prefix and reports the
  tail. Writable resume (new version) proceeds and records the tail in
  `SESSION_START.parent_scan`. Nothing is truncated: the writer never
  appends to an old segment, so the torn bytes can never be confused with
  new records. (Physical truncation was rejected: it modifies user data and
  buys nothing because resume always starts a new segment in a new version.)
- Corruption is a stop. Read-only open returns the valid prefix together
  with the error so the user can still view and export what is verifiable,
  but the session family is marked `corrupt` in the UI; writable resume is
  refused with `SessionError.ParentCorrupt`. The user may start a new
  family and attach the old one as `related`. Never auto-skip the bad
  record (I3, I9).

### 5.3 Multi-segment rules

Given the rotation order in section 4.2:

| Observed | Verdict |
|---|---|
| Segments 1..K all sealed, no K+1 | Clean rotation then crash before creating K+1, or clean close before rotation. Prefix = all. |
| 1..K-1 sealed, K unsealed, no K+1 | Normal: K is the active segment at crash. Apply 5.2 to K. |
| 1..K-1 sealed, K has header only | Crash after step 2 or 3 of rotation. Prefix = through K-1. Fine. |
| Any unsealed segment followed by another segment file | Impossible under 4.2 ordering. `Corrupt`. |
| Header of K invalid or short, K is the last file, K-1 sealed | Crash in step 2 while writing the header. Treat as torn: prefix = through K-1; report the partial header as `Torn`. |
| Segment 1 is the only file and its header is short (fewer than 64 bytes, bytes a prefix of the magic) | Crash while writing the first header, before any acknowledgement. No acked data exists: scan returns Ok, zero records, `tail = Torn(0, len)` with a warning; the file is left in place. A full-length header with a bad CRC or a non-magic prefix stays `SegmentHeaderInvalid`. |
| File name gap (seg-000003 without seg-000002) | `Corrupt`. |
| `first_seq` of K != last seq of K-1 + 2 (the +1 is K-1's seal) | `Corrupt`. |

### 5.4 Chain verification (families with several versions)

A family (section 8.5) is a chain v001 <- v002 <- ... via
`SESSION_START.parent`. Replay opens each version in order and checks:
`SESSION_START.parent_last_seq` of v(n+1) equals the recovered last data
seq of v(n) (a mismatch means the parent changed after the child was
created, which is impossible without external tampering: `Corrupt`), and
seq numbering continues (`first_seq` of v(n+1) = `parent_last_seq + 1`).

### 5.5 Session-directory states

| State | Definition | Open read-only | Open writable |
|---|---|---|---|
| `incomplete` | directory exists, no `wal/seg-000001.wal` with a valid header and a valid `SESSION_START` | listed as incomplete, nothing read | never; a new version number is taken |
| `open` | valid start, no `SESSION_CLOSE`, lock free | allowed, tail reported | resume only (new version) |
| `locked` | lock held by a live process | allowed | refused `SessionError.Locked` |
| `closed` | last data record is `SESSION_CLOSE` | allowed | resume only (new version) |
| `corrupt` | section 5.2 corruption | prefix only, with error | refused |

## 6. Durability contract

### 6.1 Definition of durable

A record is durable when the bytes of the record and of every earlier
record in the same version have been written to the segment file and the
platform "flush to stable storage" primitive of section 10 has returned
success for that file, and, for the first record of a new segment, the
directory entry of the segment has been flushed (where the OS supports
it). `durable_seq` is the highest seq that is durable. It is published by
the writer thread only (section 7), monotonically non-decreasing, and is
the only thing the display gate (6.4) and the acknowledgement path consult.

### 6.2 fsync policy: group commit without a timer

The writer thread loop (one iteration = one group commit):

1. Block on the queue for the first item.
2. Drain further items without blocking until the batch reaches
   `BATCH_MAX_BYTES = 4 MiB` or `BATCH_MAX_RECORDS = 1024` or the queue is
   empty.
3. Encode the records (CRC per record), concatenate into one buffer, and
   write it with a loop over `os.write` until every byte is written (short
   writes are legal and must be handled). If the batch would cross
   `SEGMENT_MAX_BYTES`, split at a record boundary and rotate (section 4.2)
   between the parts.
4. Flush (section 10 primitive).
5. Publish `durable_seq = last seq of the batch`, then resolve the
   per-record futures/ack callbacks, then update metrics.

There is no commit timer: the fsync latency sets the batch size naturally.
On an idle queue a single record is flushed immediately, so a lone
`POINT` or `NOTE` is durable within one fsync.

Settings (constants in `sadi/store/wal.py`, overridable by the writer's
pydantic `WalConfig` for tests): `BATCH_MAX_BYTES`, `BATCH_MAX_RECORDS`,
`SEGMENT_MAX_BYTES`, `MAX_PAYLOAD`.

### 6.3 Directory durability

fsync of the containing directory is required after: creating a session
directory, creating `seg-000001.wal`, every rotation (new segment file),
every rename of a snapshot, export, export sidecar or manifest cache. On
Windows the directory is flushed through ctypes (section 10, UNVERIFIED
until run on Windows).

### 6.4 Display gate

The acquisition pipeline (B3) enqueues each raw batch as a `RAW_BLOCK`
record and receives the assigned `seq` synchronously (the queue assigns seq
at enqueue, so seqs are allocated in enqueue order; see 7.1). It holds the
block in a small "pending" map and forwards it to analysis and display
only when `durable_seq >= seq` (the writer thread publishes `durable_seq`
through a `threading.Condition`-backed watch; the pipeline awaits it off the
asyncio loop). Nothing undurable is drawn (I6).

Trace frames sent to the browser carry `durable_seq` and `enqueued_seq`;
the UI shows a "writing..." indicator when `enqueued_seq - durable_seq`
corresponds to more than `DISPLAY_LAG_WARN_MS = 250` ms, and the status bar
shows "ALL DATA SAVED" or "SAVING (n blocks)" at all times.

If `durable_seq` makes no progress for `STALL_TIMEOUT_S = 5` seconds while
records are queued, the writer is declared stalled: acquisition is stopped
(device `Stop` is sent), a `MARKER(kind="acquisition_stopped",
data={"reason": "store_stalled"})` is enqueued, and the UI gets
`StoreError.Stalled` with the hint "The data disk is not responding. Data
already shown is safe; new data is held in memory. Free space or change
disk, then resume." The queue is NOT discarded (7.3).

The "flag as unsaved and show anyway" alternative mentioned in B3 is
rejected: a value on screen that might vanish contradicts the requirement.

### 6.5 Disk full and I/O errors

In the API error taxonomy (`sadi.core.errors.StoreCode`) the writer failures
`Backpressure`, `DiskFull`, `Closed` and `Stalled` are the codes
`backpressure`, `disk_full`, `closed` and `stalled`, each with a user hint
and an HTTP 500 problem body.

Pre-flight at session create and resume: free space on the data root must
be at least `MIN_FREE_BYTES = 2 GiB` or the create fails with
`SessionError.DiskSpace` (hint names the path and the shortfall). The
writer re-checks free space at every rotation and every
`FREE_SPACE_CHECK_S = 10` s: below `LOW_SPACE_WARN_BYTES = 512 MiB`
(about 14 min of raw) a `MARKER(kind="low_disk_space")` is written and the
UI warns; below `LOW_SPACE_STOP_BYTES = 128 MiB` acquisition is stopped
loudly (same path as a stall) while a stopped session still has headroom
to write its remaining queue, close record and a snapshot.

On any `OSError` from open, write, flush or rename in the writer:

1. The writer enters state `FAILED` with the typed error (`ENOSPC` ->
   `StoreError.DiskFull`, `EIO`/others -> `StoreError.IoError`), stops
   taking new work from the queue, and publishes the error. It never retries
   a failed fsync on the same fd and assumes success (Linux may drop the
   dirty pages after an fsync error; the only safe assumption is that the
   batch is not durable).
2. Acquisition stops loudly (as in 6.4). All undurable records (the failed
   batch and the queue) are kept in memory in order.
3. Retry and Save-elsewhere UI actions are NOT implemented yet; the only
   shipped recovery is the spill in step 4 (Close session retries it).
4. `SessionService.close` (and so `shutdown`, at process exit) handles a
   writer whose `close()` fails: it takes `writer.undurable_records()` and
   writes them with `sadi.store.spill.write_spill` as a plain segment file
   (same framing, header carries the session uuid and the first seq; one file
   per dense seq run). Each file is written to a hidden tmp name, fsynced,
   published with a no-replace rename and the directory fsynced, so an
   existing spill is never overwritten. Locations are tried in order:
   `<data-root>/spill/`, the user data directory (`~/.local/share/sadi/spill`,
   `%LOCALAPPDATA%\sadi\spill`, `~/Library/Application Support/sadi/spill`),
   then the OS temp dir (`sadi-spill-*.wal`); every attempt and the final path
   are logged. The file name is deterministic (`sadi-spill-<session uuid>-<first seq>.wal`),
   so a Close retry that spills the same records reuses the existing file instead of piling up
   copies; a retry with different records for the same key is written beside it under a
   content-hash suffix (nothing is overwritten). Spill files are picked up at next start by
   `import_all_spills` and become a new version with a parent link. When the spill directly
   continues the parent's verified records, the new version is self-contained: the parent's
   verified records (calibration, tare, points; seals dropped) followed by the spill frames,
   renumbered densely from 1, so it resumes and downloads like any session. The parent is
   never modified and stays on disk; a complete successor supersedes an `incomplete` parent in
   the setup list. A spill that does not continue the parent is kept alone as a fragment
   version (`continuity_ok=false`), never dropped. Byte-identical spill copies in two
   locations import once. If NO location accepts the
   records, close returns HTTP 409 (`undurable_records`), the session and its
   in-memory writer stay open, and the user can fix the disk and press Close
   session again; records are never dropped silently. If the process is
   forced to exit in that state the loss is logged at CRITICAL.

### 6.6 Latency budget (DS3 acceptance 3 measures these)

Target on an internal SSD: p50 group commit <= 10 ms, p99 <= 50 ms, at the
sustained 612 kB/s plus 10 markers/s. Display latency added by the gate is
one group commit. On HDD or macOS `F_FULLFSYNC`, p99 up to 200 ms is
acceptable and only increases batch size, never loses data.

## 7. Writer thread (DS8)

### 7.1 Ownership and queue

One `threading.Thread(name="sadi-wal-writer", daemon=False)` owns the
`WalWriter` instance and the open segment fd exclusively. Nobody else
touches `wal/`. Producers call `WriterHandle.submit(record) ->
Result[Seq, StoreError]` from any thread:

- `submit` assigns `seq` under the handle's lock (so seq order equals queue
  order), encodes nothing yet, and puts `(seq, record)` into a bounded
  `queue.Queue`. Bound: `QUEUE_MAX_BYTES = 64 MiB` of estimated payload
  (about 100 s of raw) and `QUEUE_MAX_ITEMS = 65536`.
- If the bound is reached, `submit` blocks for at most `SUBMIT_TIMEOUT_S =
  2` s, then returns `Err(StoreError.Backpressure)`. The pipeline treats
  that as a stall (6.4): stop acquisition loudly. The Rust acquisition
  thread's own bounded channel (R8) backs up behind it; the FTDI FIFO may
  then overflow at the hardware level, which the device reports as a
  saturation purge and which is recorded as `RAW_JUNK(reason=3)` once the
  writer recovers. Data is never dropped by SADI; it is only ever lost by
  the device, visibly, after a loud stop.
- `submit` never drops, coalesces or reorders.

### 7.2 Metrics

Published as a pydantic `WriterMetrics` snapshot, updated per batch, read
by the UI status bar and the pipeline:

`queue_depth_items`, `queue_depth_bytes`, `enqueued_seq`, `durable_seq`,
`last_batch_records`, `last_batch_bytes`, `fsync_latency_ms` (last, p50,
p99 over a 256-sample ring), `submit_wait_ms` (same ring),
`segment_no`, `segment_bytes`, `free_bytes`, `state`
(`RUNNING`, `ROTATING`, `STALLED`, `FAILED`, `DRAINING`, `CLOSED`),
`error` (typed, or null). Every state transition is logged at INFO with
the metrics; `FAILED` and `STALLED` at ERROR.

### 7.3 Shutdown and failure

`close()` sets `DRAINING`, refuses new submits (`Err(StoreError.Closed)`),
writes every queued record, writes `SESSION_CLOSE`, flushes, releases the
lock and joins. The final segment is deliberately left unsealed: a seal
means "rotated", and the reader's last-segment rule (5.3) already covers a
clean close. On `FAILED` the queue is preserved as in 6.5.

Thread-safety contract: `WalWriter` methods are called only on the writer
thread; `WriterHandle` is the thread-safe facade. CC1 ~DK06Q2F documents the
lock order (`WriterHandle._lock` is a leaf lock; nothing is acquired while
holding it).

## 8. Session directories (DS4)

### 8.1 Layout

```
<data-root>/sessions/<dir-name>/
    manifest.json          derived cache (8.4); atomic replace
    lock                   single-writer lock (8.3)
    wal/seg-000001.wal     ... primary data (sections 3-5)
    snapshots/             derived (9.1)
    exports/               derived (9.3)
<data-root>/sessions/.staging/   never used; reserved
<data-root>/spill/               emergency spill (6.5 step 4)
```

`<data-root>` defaults to the per-user data directory (`~/.local/share/sadi`,
`%LOCALAPPDATA%\sadi`, `~/Library/Application Support/sadi`) and is
overridable by `--data-root`. Network and WSL-drvfs roots trigger section
10's warnings.

### 8.2 Naming and exclusive creation

`dir-name = <family>.v<NNN>` where `family = <YYYYMMDD>T<HHMMSS>Z-<slug>`
(UTC creation time of v001, slug = up to 32 chars of `[a-z0-9-]` derived
from operator and specimen, default `session`) and `NNN` is a zero-padded
version from 001 to 999. Example: `20261108T153000Z-copper-short.v001`.

Create procedure (`create_session(root, meta) -> Result[SessionHandle,
SessionError]`):

1. Pre-flight free space (6.5) and filesystem warnings (section 10).
2. `os.mkdir(<root>/sessions/<family>.v001)`. `mkdir` is create-exclusive
   on every OS: `FileExistsError` means the name is taken; increment `NNN`
   and retry (bounded at 999, then `SessionError.TooManyVersions`). Never
   `exist_ok`, never `rmtree`.
3. `os.mkdir` `wal/`, `snapshots/`, `exports/`.
4. Acquire the lock (8.3).
5. Create `wal/seg-000001.wal` exclusively, header, fsync file.
6. Write the `SESSION_START` record through the writer and wait for
   `durable_seq >= 1`.
7. fsync the session directory and `sessions/` (the new directory entry).
8. Write the manifest cache (8.4).

A directory without a valid `SESSION_START` is `incomplete` (5.5) and is
simply skipped by listing code and never reused: a retry takes the next
version number.

### 8.3 Lock

File `lock`, created exclusively on the first open and kept forever (it is
never deleted; deleting it would be a modification). Locking uses the OS
process-scoped lock on an open handle so that it is released by the kernel
when the process dies, which makes stale locks impossible on local
filesystems:

- POSIX: `fcntl.flock(fd, LOCK_EX | LOCK_NB)`.
- Windows: `msvcrt.locking(fd, LK_NBLCK, 1)` on byte 0.

The writer holds the fd for the session's life and writes nothing to the
file except, at acquisition, appending one line `pid=<n> host=<h>
started=<rfc3339>` for humans (append-only, O_APPEND). On lock failure:
`SessionError.Locked(pid_hint)` from the last line of the file. Network
filesystems: see section 10; locks there are advisory at best, which is one
reason writable sessions on them are refused by default.

### 8.4 Manifest cache

`manifest.json` is a derived cache so that UIs and `ls` can see what a
session is without parsing the WAL. It is regenerated from `SESSION_START`
and `SESSION_CLOSE` records and from the scan report, via `atomic_replace`
(section 10) with tmp file `manifest.json.tmp-<pid>-<rand>` created
exclusively in the same directory. Losing it loses nothing (I7). It is
written at create, at close, and at read-only open if missing or stale
only when the session is opened writable (a read-only open never writes,
I8; it reports "manifest stale" instead).

`SessionManifestV1` (pydantic, frozen):

```
v: 1
format_version: 1               segment header format this version uses
session_uuid: UUID
dir_name: str
family: str
version: int
parent: str | None              parent dir_name
parent_last_seq: int | None
root_family_created: datetime
created: datetime
code_version: {sadi: str, git_sha: str | None, python: str, platform: str}
lab_module: str                 e.g. "sadi.labs.lctt"
specimen: dict                  lab-defined, copied from SESSION_START
device: {transport: str, firmware: str | None, adc_range_codes: list[int], sample_rate_hz: float}
state: "open" | "closed" | "crashed" | "corrupt"
closed: datetime | None
last_seq: int | None
tail: {kind: "none" | "torn" | "partial" | "corrupt", segment: int, offset: int, bytes: int} | None
```

#### 8.4.1 Optional `plugins` field (provenance)

The manifest may carry `plugins: [{id: str, version: str}, ...]`, the plugins active when
that session version was made (see [Plugins](plugins.md)). It is optional and backward
compatible: absent means empty, and the manifest `v` stays 1. The WAL is untouched: this
is derived cache data only (I7), so no record type or frame changes. `create` takes the
list; `resume` takes a new list or inherits the parent's. On reopen the caller may pass the
available plugins (id to version); a recorded plugin that is missing or at a different
version produces `PluginWarning`s alongside an `Ok` result. It never fails the open, and
stored data stays readable without the plugin.

### 8.5 Families, versions and seq continuity

All versions of a family share one seq space: v001 starts at 1; v(n+1)
starts at `parent_last_seq + 1`, where `parent_last_seq` is the last
verified data seq of v(n) (the parent's trailing seal, if any, is counted;
section 5.3's `+2` rule covers it). One integer therefore orders every
record a user ever produced for a specimen, snapshots cite one integer, and
replay is the concatenation of the chain.

### 8.6 Resume

`resume_session(parent_dir) -> Result[SessionHandle, SessionError]`:

1. Open the parent read-only and scan (section 5). `Corrupt` -> refuse.
   `Locked` -> refuse. Torn or clean -> continue.
2. Create the next version directory per 8.2 with `parent` set.
3. Its `SESSION_START.parent_scan` carries the parent's `ScanReport`
   (tail kind, offset, length, SHA-256 of the torn bytes) so the forensic
   trail is in the primary record.
4. The pipeline re-sends the decoding `SETTINGS` records (ADC range codes
   etc.) before the first `RAW_BLOCK` of the new version; replay of the
   chain would otherwise need the parent for them, and each version must
   be decodable alone.

The parent is never modified. Review (read-only) of an `open` session with
a torn tail shows the verified prefix plus a "recovered after crash;
N bytes unverifiable tail" banner.

Stale data-root lock after a crash: `acquire` reports `LockStale` (OS lock free, dead pid
recorded) and changes nothing. The user-visible recovery is `sadi serve --recover-stale`
(or `sadi-store recover --recover-stale`); it only rewrites the lock file's holder line and
never touches session data (I9: loud, never silent, never destructive).

## 9. Snapshots and exports (derived)

### 9.1 Snapshot files (DS5)

Path: `snapshots/snap-<covers_seq:012d>-<YYYYMMDDTHHMMSSffffffZ>.snap`. The
file is exactly one WAL frame (section 3.1) of type `SNAPSHOT` (code 0x0A is
the *reference* record in the WAL; the snapshot file itself uses frame type
0x0A as well, with `seq = covers_seq`), payload JSON `SnapshotV1`:

```
v: 1
covers_seq: int                 replay state after applying records 1..covers_seq
prefix_hash: hex                section 9.2
code_version: {...}             as in the manifest
lab_module: str
state: dict                     lab-defined replay state (pydantic model_dump)
```

Reusing the frame gives the snapshot a CRC and torn detection for free.

Write procedure (`write_snapshot(session, state, covers_seq)`), every step
a failpoint:

1. Create `snapshots/.snap-<covers_seq>-<pid>-<rand>.tmp` exclusively
   (dot-prefixed so listings ignore it).
2. Write the frame; fsync(file); close.
3. Compute the final name; if it already exists (same covers_seq written
   twice in the same microsecond, practically impossible) append
   `-<rand>`; rename tmp -> final with the no-replace rename primitive
   (section 10), never `atomic_replace`.
4. fsync(dir `snapshots/`).
5. Enqueue `SNAPSHOT_REF` to the WAL (informational; recovery does not
   depend on it).

Snapshot cadence: after every `POINT`, `EDIT` and `SESSION_CLOSE`, and at
most once per `SNAPSHOT_MIN_INTERVAL_S = 5` s otherwise. Snapshots are
never pruned automatically; a `sadi store prune-snapshots` command may
remove all but the newest K valid ones on explicit user request, and even
then it moves them to `snapshots/.pruned/` rather than deleting.

Recovery (`load_latest_snapshot`): list `snap-*.snap`, sort by covers_seq
descending, for each: parse the frame (CRC), check `covers_seq <=
last_verified_seq`, recompute `prefix_hash` at `covers_seq` from the WAL
scan and compare; the first match wins; replay the WAL from
`covers_seq + 1`. No match: replay from 1. A snapshot that fails any check
is logged at WARNING with the reason and ignored (I5 makes this safe:
either it is complete or it never got its final name). Leftover `.tmp`
files are ignored and never deleted.

### 9.2 prefix_hash

The reader maintains `h = sha256()`; for each verified data record it
updates `h` with the 12 bytes `seq (u64 LE) || crc32c (u32 LE)`.
`prefix_hash(n)` is `h.hexdigest()` after record `n`. It identifies the
exact verified prefix cheaply (12 bytes per record, no payload re-hash) and
is what snapshots and exports cite.

### 9.3 Exports (DS7)

Path: `exports/<kind>/<NNNN>-<YYYYMMDDTHHMMSSZ>-<basename>.<ext>` with
sidecar `<same>.prov.json`. `NNNN` is one more than the highest existing
number under `exports/<kind>/` (listing at write time; the lock guarantees a
single writer). Exports never overwrite: a name collision takes the next
number.

Procedure (`write_export(session, kind, basename, ext, payload: bytes)`):

1. Create `exports/<kind>/.<name>.tmp-<pid>-<rand>` exclusively; write;
   fsync; close.
2. Rename no-replace to the final name.
3. Create the sidecar the same way (tmp, fsync, rename no-replace).
4. fsync(dir).
5. Enqueue `EXPORT_REF`.

Server wiring (audit1 #22): every download from `GET /api/export/{id}`
is also written through `write_export` into `exports/<id>/`, and the
response carries `X-SADI-Saved` (the relative path, or `failed`; a failed
copy never blocks the download). Rendered figures are uploaded by the UI to
`POST /api/export/figure/{figure_id}` and kept under `exports/figure/` with
the session name in the basename. Snapshots: `SessionService` calls
`snapshot.write_snapshot` after each durable command that appended a `POINT`
or `EDIT`, after any other command at most every `SNAPSHOT_MIN_INTERVAL_S`
(5 s), and once at session close (after the writer drained). The server does not
enqueue the informational `SNAPSHOT_REF` (it would change the WAL record
count of the recording). A snapshot of an
already-snapshotted `covers_seq` is skipped; names are never replaced. A
failed snapshot is logged and never fails or blocks the request (derived
data, I7); after SIGKILL recovery uses the newest snapshot whose prefix hash
matches and replays the WAL tail.

Session families (audit1 #12, #34, #41): the slug is ASCII-folded; two
sessions created in the same second with the same slug become distinct
families (`name`, `name-2`, ...) instead of silently becoming versions of
one family. `GET /api/sessions` marks older versions `latest: false` with
`latest_name`, and `POST /api/sessions/resume` returns `newer_versions`
when a later version exists. A clean close records `last_seq` in the
manifest so closed sessions are not reported stale.

`ExportProvenanceV1`: `v`, `kind`, `path`, `sha256` (of the export bytes),
`size`, `created`, `covers_seq`, `prefix_hash`, `snapshot_path` (or null),
`code_version`, `lab_module`, `parameters` (dict: fit window, units, sig
figs...). An export without a sidecar is `incomplete` and is listed as
such, never trusted. The regeneration test (DS7 acceptance 2) deletes
`exports/` and `snapshots/` entirely and rebuilds byte-identical exports
from the WAL chain.

## 10. Per-OS durability table

Primitives live in `sadi/store/durable.py` (DS2), all returning typani
`Result[None, DurableError]` (or `Result[int, ...]` for fds). The table
states the primitive chosen, why, and the residual risk accepted.

| Operation | Linux | macOS | Windows | Residual risk |
|---|---|---|---|---|
| `fsync_file(fd)` | `os.fsync(fd)`; ext4/xfs/btrfs with barriers flush the drive cache. `fdatasync` is NOT used: appends change file size, which is metadata the reader needs. | `fcntl.fcntl(fd, fcntl.F_FULLFSYNC)`; plain `fsync` only reaches the drive cache on macOS. If `F_FULLFSYNC` fails with `ENOTSUP`/`EINVAL` (exFAT, some externals), fall back to `os.fsync` once per fd, log at WARNING once, set `WriterMetrics.durability_downgraded = True` and show it in the UI. | `os.fsync(fd)` -> `_commit` -> `FlushFileBuffers`: flushes data and the file's metadata and issues a cache flush unless the user disabled "write-cache buffer flushing" on the device. | Drives that lie about cache flush; user-disabled flushing on Windows; virtualised disks. Documented, not mitigable in software. |
| `fsync_dir(path)` | `fd = os.open(path, O_RDONLY \| O_DIRECTORY)`; `os.fsync(fd)`. | Same call; on APFS it is accepted and `F_FULLFSYNC` on the dir fd is attempted first, `fsync` fallback. | `CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ\|WRITE\|DELETE, NULL, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS)` then `FlushFileBuffers(handle)` and `CloseHandle`, via ctypes (`_win_flush_dir`); failures are logged at ERROR and returned as `DurableIo`. NTFS also journals metadata changes, so a created file is reachable after a crash once its own flush returned. **UNVERIFIED: not yet run on Windows.** | Non-NTFS data roots on Windows (FAT32/exFAT USB sticks) can lose a just-created file after power loss. Pre-flight warns when `GetVolumeInformationW` does not report NTFS/ReFS. Directory flush behaviour on FAT/exFAT is unverified. |
| `create_exclusive(path)` | `os.open(path, O_WRONLY \| O_CREAT \| O_EXCL \| O_CLOEXEC, 0o644)` | same | `os.open(path, O_WRONLY \| O_CREAT \| O_EXCL \| O_BINARY)`; the CRT maps `O_EXCL` to `CREATE_NEW`. `O_BINARY` is mandatory or the CRT would translate bytes. Sharing-violation retry (below). | NFS v2/3 `O_EXCL` is not atomic; refused root by default. |
| `open_append(path)` | `O_WRONLY \| O_APPEND \| O_CLOEXEC` | same | `O_WRONLY \| O_APPEND \| O_BINARY` | None. Writer owns the fd for the segment's life. |
| `rename_noreplace(src, dst)` | `renameat2(AT_FDCWD, src, AT_FDCWD, dst, RENAME_NOREPLACE)` via ctypes: atomic and race-free. On `ENOSYS`/`EINVAL`/`ENOTSUP` (old kernel, filesystem without support) fall back to `os.link` + `os.unlink`. Then `fsync_dir`. | `os.link(src, dst)` (fails if dst exists) then `os.unlink(src)`, then `fsync_dir`. **UNVERIFIED: not run on macOS.** | `ctypes MoveFileExW(src, dst, MOVEFILE_WRITE_THROUGH)` without `REPLACE_EXISTING`: `ERROR_FILE_EXISTS`/`ERROR_ALREADY_EXISTS` become `DurableExists`. Sharing-violation retry. **UNVERIFIED: not run on Windows.** | link+unlink is not a single atomic step: a crash between the calls leaves both names (the data is intact; recovery must tolerate a duplicate name). |
| `atomic_replace(tmp, dst)` (derived files only: manifest cache) | `fsync_file(tmp)`; `os.replace` (atomic `rename(2)`); `fsync_dir(parent)`. | same, `F_FULLFSYNC` on tmp. | `fsync_file(tmp)`; `ctypes MoveFileExW(tmp, dst, MOVEFILE_REPLACE_EXISTING \| MOVEFILE_WRITE_THROUGH)` (atomic on the same NTFS volume; `os.replace` lacks `WRITE_THROUGH`); no dir fsync. Sharing-violation retry. | Cross-volume paths are not atomic: tmp is always created in `dst`'s directory, enforced by the primitive (`DurableError.CrossDevice` if parents differ). |
| Sharing-violation retry | n/a | n/a | On `PermissionError` with `winerror in (5, 32)` (access denied, sharing violation: antivirus, indexer, Explorer preview) retry with backoff 10, 20, 40, ... ms, capped at 500 ms per attempt, total `SHARING_RETRY_TOTAL_S = 5` s, then `DurableError.SharingViolation(path, attempts)`. Every retry is logged at WARNING. Only for rename/replace/create of *derived* and *new* files; never used to work around a lock (I8). | Persistent AV holds beyond 5 s fail loudly; the UI hint says to exclude the data root from real-time scanning. |
| Directory create | `os.mkdir` (atomic, exclusive) | same | same | none |
| Lock | `fcntl.flock` | `fcntl.flock` | `msvcrt.locking` | Network FS: unreliable (refused by default). |
| Free space | `shutil.disk_usage(root)` | same | same | Quotas not reflected on some FS. |
| Filesystem detection and warnings | Parse `/proc/mounts` for the mount containing root: types `9p`, `drvfs` (WSL /mnt/c) -> WARNING "fsync and locks on /mnt/c are not reliable; use the Linux filesystem (e.g. ~/sadi-data)". Types `nfs*`, `cifs`, `smb*`, `fuse.sshfs`, `fuse.rclone` -> network: writable refused unless `--allow-network-fs`. | `statfs` f_fstypename `nfs`, `smbfs`, `afpfs` -> network as Linux. `exfat`, `msdos` -> WARNING (no `F_FULLFSYNC`). | `GetDriveTypeW` == `DRIVE_REMOTE` or UNC path -> network as Linux. `GetVolumeInformationW` fs name not `NTFS`/`ReFS` -> WARNING (dir durability). `DRIVE_REMOVABLE` -> INFO. | Detection is best effort; the warning is recorded as a `MARKER(kind="storage_warning")` in the WAL itself so it travels with the data. |

WSL specifics: the dev machine runs WSL2. The default data root under
`~/.local/share/sadi` is on ext4 inside the VM and gets full Linux
semantics; `/mnt/c/...` is drvfs/9p where `fsync` may be a no-op and
`flock` may fail with `ENOLCK`. The pre-flight therefore warns and the lock
primitive treats `ENOLCK` as `DurableError.Unsupported` which makes
writable open fail unless `--allow-network-fs` is given.

## 11. Failpoints

`sadi/store/failpoints.py` (DS2) provides a process-wide registry used by
every store module and driven by the crash harness (DS6):

```
failpoint(name: str) -> None
```

Public, cheap when inactive (one dict lookup; registry is frozen after
first activation). Activation via environment variable at interpreter
start, `SADI_FAILPOINTS="name=action[,name=action...]"`, or
programmatically `failpoints.configure({...})` in tests. Actions:

| Action | Effect |
|---|---|
| `kill` | `os._exit(137)` immediately (no cleanup, no flush; simulates SIGKILL/TerminateProcess from inside). |
| `abort` | `os.abort()` (core-dump style). |
| `sleep:<ms>` | `time.sleep` (used for slow-fsync and stall tests). |
| `error:<errno>` | raise `OSError(errno, ...)` at the call site (e.g. `error:28` for ENOSPC, `error:5` for EIO). |
| `once:<action>` | the action fires on the first hit only. |
| `nth:<n>:<action>` | fires on the n-th hit. |
| `prob:<p>:<action>` | fires with probability p (seeded by `SADI_FAILPOINT_SEED`). |

Every hit (fired or not) is logged at DEBUG with a counter; fired actions at
WARNING. Named failpoints, which implementing tickets MUST place exactly
here (DS6 depends on the names):

| Name | Location |
|---|---|
| `wal.encode.before` | writer, before encoding a batch |
| `wal.write.partial` | writer, after the first `os.write` of a batch when the batch is > 1 record (harness truncates the batch mid-record: the action `kill` here yields a torn record) |
| `wal.write.after` | after all bytes of the batch are written, before fsync |
| `wal.fsync.before` | immediately before the platform flush |
| `wal.fsync.after` | after flush, before `durable_seq` publish |
| `wal.publish.after` | after `durable_seq` publish |
| `wal.rotate.after_seal_write` | between writing the seal and its fsync |
| `wal.rotate.after_seal_fsync` | between step 1 and 2 of 4.2 |
| `wal.rotate.after_create` | after creating the new segment, before its header |
| `wal.rotate.after_header` | after header write, before header fsync |
| `wal.rotate.after_header_fsync` | between step 2 and 3 |
| `wal.rotate.after_dir_fsync` | between step 3 and 4 |
| `session.create.after_mkdir` | after the version directory exists, before subdirs |
| `session.create.after_lock` | after lock acquisition |
| `session.create.after_segment` | after `seg-000001.wal` header fsync, before `SESSION_START` |
| `session.create.after_start_record` | after `SESSION_START` durable, before manifest cache |
| `session.manifest.after_tmp_write` | manifest tmp written, before fsync |
| `session.manifest.after_tmp_fsync` | before replace |
| `session.manifest.after_replace` | before dir fsync |
| `snapshot.after_tmp_write` | snapshot tmp written, before fsync |
| `snapshot.after_tmp_fsync` | before rename |
| `snapshot.after_rename` | before dir fsync |
| `snapshot.after_dir_fsync` | before `SNAPSHOT_REF` enqueue |
| `export.after_tmp_write` | export tmp written |
| `export.after_rename` | export renamed, sidecar not yet written |
| `export.after_sidecar_rename` | before dir fsync |
| `durable.fsync_file` | inside the primitive (for `error:` injection on every flush) |
| `durable.write` | inside the write loop (for `error:28`) |
| `durable.rename` | inside rename primitives (for `error:32`-style sharing violations on Windows tests; the harness also holds a real handle) |

## 12. Crash-recovery test plan (DS6, J5)

### 12.1 Harness

`python/tests/crash/harness.py`:

- Spawns `python -m sadi.store.crashee <session-root> <scenario>` as a
  subprocess with `SADI_FAILPOINTS` set, or with no failpoint and a random
  kill delay. The crashee runs a real `WriterHandle` fed by a synthetic
  packet source at the real rate (1000 packets/s of 612 bytes, generated
  deterministically from a seed so content is checkable) plus markers,
  points and edits at random intervals, snapshots per 9.1 cadence, and
  exports every few seconds.
- The crashee writes an **oracle log** to a file outside the session root
  (`<tmp>/oracle.log`), one line per event, flushed per line: `ack <seq>`
  after each `durable_seq` publish (every seq is covered by the highest
  ack), `snapshot <path> <covers_seq>`, `export <path>`, `fsync_offset
  <segment> <offset>` after every flush. The oracle log itself is
  irrelevant to the system under test; its last line may be torn and is
  dropped.
- Kill: `Popen.kill()` (SIGKILL on POSIX, `TerminateProcess` on Windows)
  at a random time in [0.1, 5] s, or let the failpoint `kill` fire.
- Recovery: open the session read-only in the harness process; replay;
  assert section 12.3.
- Repeat: `>= 200` iterations per OS in `.github/workflows/crash.yml`
  (ubuntu, windows, macos), seeds logged; on failure upload the session
  directory and the oracle log as artifacts.

### 12.2 Scenarios

| Scenario | Mechanism | Targets |
|---|---|---|
| `random-kill` | random delay kill | I1, I2, I3, I4, I5 |
| `every-failpoint-kill` | iterate every failpoint in section 11 with `kill`; at least 3 runs each | all steps of 4.2, 8.2, 9.1, 9.3 |
| `partial-record` | `wal.write.partial=kill` | torn tail classification |
| `power-loss-emulation` | after a random kill, copy the session dir, truncate each segment copy to the last `fsync_offset` from the oracle, then append 0-4096 random bytes (simulating unflushed and garbage sectors); recover from the copy | I1, I2 on the truncated copy; torn-tail vs corruption rule (5.2) |
| `bit-flip` | after a clean close, flip 1-8 random bits in a random segment and recover (hypothesis property test in DS3 also covers this at unit level) | I3: never an accepted corrupt record; mid-log flip is `Corrupt`, tail flip is `Torn` |
| `enospc` | `durable.write=error:28` after N batches | 6.5: FAILED state, queue preserved, Retry path re-emits same seqs, no gap |
| `eio-on-fsync` | `durable.fsync_file=once:error:5` | writer FAILED, no durable_seq advance, no ack for that batch |
| `slow-fsync` | `durable.fsync_file=sleep:300` | backpressure metrics, display gate holds, no drop; `sleep:6000` triggers the 5 s stall stop |
| `rotate-kill` | small `SEGMENT_MAX_BYTES` (1 MiB) and `wal.rotate.*=kill` | 5.3 table |
| `snapshot-kill` | `snapshot.*=kill` | I5: file at final path is complete or absent; `.tmp` leftovers ignored |
| `export-kill` | `export.*=kill` | export without sidecar is `incomplete`; regeneration reproduces it |
| `concurrent-open` | second crashee tries writable open while first is alive | I8: `Locked`; after kill, resume succeeds without stale-lock handling |
| `kill-during-jobs` (J5) | crashee also runs the job pool (J1) with Monte Carlo jobs on the current state while being killed; worker processes are also killed in random order | I1-I5 hold; worker processes never wrote into the session dir (assert directory listing diff is empty apart from the writer's own files); snapshot is old-or-new |
| `windows-sharing` | Windows only: harness holds an open handle on the manifest tmp/dst and on a snapshot dst while the crashee writes | retry succeeds within 5 s, or fails loudly with `SharingViolation`; no torn file |
| `readonly-is-readonly` | open an existing session read-only, list, replay, export nothing; compare a full recursive hash of the directory before and after | I8, DS4 acceptance 3 |

### 12.3 Assertions after every kill

1. `ScanReport` succeeds or reports `Torn`; `Corrupt` is a test failure
   except in `bit-flip` mid-log cases where it is the expected outcome.
2. Recovered seqs are exactly `1..N` with no gaps (I1) and `N >= max ack`
   from the oracle (I2).
3. Every recovered `RAW_BLOCK` payload matches the seeded generator for
   its seq (I3; content check, not just CRC).
4. The set of files before the kill (oracle `snapshot`/`export` lines) is
   a subset of the files after; no file's content changed (I4; the
   harness keeps SHA-256 of each committed file as it appears).
5. Every `snap-*.snap` and export at a final path is complete (parses, CRC
   or sidecar sha256 matches) (I5).
6. Replaying twice gives identical state bytes (I10).
7. Resume creates `v(n+1)` and leaves `v(n)` byte-identical (hash the tree).

### 12.4 Unit-level tests (DS3, DS4, DS5, DS7)

- Hypothesis: random record sequences -> encode -> random truncation point
  -> decode yields exactly the records before the cut (I1) and a `Torn`
  tail; random bit flips never yield an accepted record with wrong bytes
  (I3).
- Golden vectors: `python/tests/store/vectors/*.wal` with a documented
  byte layout, so the framing in section 3 is pinned by bytes.
- `prefix_hash` vectors.
- Throughput: 60 s at 612 kB/s plus markers; assert p99 batch latency
  recorded; publish numbers in docs/store/wal.md.

## 13. Failure modes table

| # | Failure | Detection | Behaviour | Data at risk | Recovery |
|---|---|---|---|---|---|
| F1 | Process killed mid-record | reader: torn tail (5.2) | acknowledged prefix intact | the unacknowledged batch (never displayed) | resume -> new version; torn bytes recorded in `SESSION_START.parent_scan` |
| F2 | Power loss after write, before flush | same as F1 after reboot | same | same | same |
| F3 | Power loss between seal fsync and next segment create | 5.3 row 1 | none | none | resume |
| F4 | Kill between snapshot rename and dir fsync (Linux) | snapshot may be absent after reboot | derived only | none | replay from WAL; older snapshot used |
| F5 | Disk full | `ENOSPC` from write, or free-space poll | writer FAILED, acquisition stopped loudly, queue held in memory | none if the user frees space or saves elsewhere; the undurable queue is spilled by close/shutdown | Close session retries the spill (6.5); Retry/Save elsewhere UI not built |
| F6 | I/O error on fsync | `OSError` | FAILED, no ack, no retry on the fd | the failed batch is re-emitted on a new segment on Retry | 6.5 |
| F7 | Store stalled (slow disk) | 5 s without durable progress | acquisition stopped loudly; display gate holds | none | resumes when the disk responds; queue drains |
| F8 | Antivirus / indexer holds a derived file on Windows | `PermissionError` 5/32 | retry up to 5 s, then loud failure | derived only | user excludes the root from scanning |
| F9 | Two instances open the same session | lock conflict | second gets `Locked` | none | none needed |
| F10 | Resume while the parent is still being written | lock held | refused | none | none |
| F11 | Device disconnect / USB fault | transport error from R5 | `DEVICE_EVENT`, acquisition stops; WAL stays open | none; the device stream itself stops | reconnect writes `DEVICE_EVENT(reconnect)` and continues in the same version |
| F12 | FTDI saturation purge (host too slow) | DLL/transport reports purge | `RAW_JUNK(reason=3, len 0)` marks the gap loudly; UI warns | device bytes lost by the hardware, visibly | not recoverable; documented gap; rate analysis is robust to marked gaps |
| F13 | Bit rot / mid-log corruption | CRC or seal hash mismatch with valid records after | `Corrupt`; read-only prefix; family marked corrupt | the corrupted record(s) | user starts a new family; forensic: torn bytes and location reported; sealed segments can be compared against backups via SHA-256 |
| F14 | Wall clock jumps | `wall_ns` non-monotonic | nothing (ordering is by seq; `mono_ns` in RAW_BLOCK) | none | none |
| F15 | Data root on network FS / drvfs | pre-flight detection | writable refused unless `--allow-network-fs`; warning marker | durability unknown | choose a local root |
| F16 | User deletes snapshots/exports/manifest | missing files | rebuilt (I7) | none | automatic on next open writable; read-only open reports stale |
| F17 | Writer thread raises a non-OSError (programmer bug) | thread exception hook | FAILED with `StoreError.Internal`, same handling as F6 (queue preserved, loud stop) | none | fix the bug; Retry path |
| F18 | Queue full (producer faster than disk for > 100 s) | `Backpressure` | acquisition stopped loudly | none in SADI; device may overflow (F12) | drain, then resume |
| F19 | Crash during session create before `SESSION_START` | directory `incomplete` | skipped, never reused | none (nothing was acknowledged) | next create takes the next version |
| F20 | Unknown record type from a newer SADI | type not in registry, CRC valid | passed through as `UnknownRecord`, logged once | none | upgrade SADI |
| F21 | Older SADI opens newer `format_version` | header check | `WalError.UnsupportedFormat`, read refused | none | upgrade SADI |
| F22 | Cross-volume tmp and dst for a derived file | parent dirs differ | `DurableError.CrossDevice` before any write | none | programmer bug; tmp is always created next to dst |
| F23 | Process exit requested with undurable records | writer not CLOSED | close/shutdown spills (6.5 step 4); 409 and writer kept if every location fails | none if a spill location is writable (else records stay in memory, close returns 409) | spill imported as new version at next start |

## 14. Schema versioning and compatibility policy

- `format_version` (segment header) governs the header layout and the
  frame rules. Bumped only for incompatible framing changes. Readers
  support every past version forever; the writer writes only the current
  one. A version's segments all share one `format_version`.
- Frame `version` byte: same policy at frame level; currently 1.
- Type codes are never reused or re-purposed. A changed meaning is a new
  code. Deprecated codes stay in the registry as "legacy, read-only".
- JSON payload `v`: additive changes (new optional fields with defaults)
  do not bump `v`; readers use `extra="allow"` and defaults. Removing or
  re-typing a field bumps `v`; the reader module keeps one pydantic model
  per `v` and an upgrade function `vN -> vN+1`, so replay always works on
  the newest model.
- Snapshot `state` is lab-module owned; the lab module declares its own
  `state_version`, and a mismatch simply invalidates the snapshot (replay
  from WAL, which is lab-version independent because it stores inputs,
  not results).
- `RAW_BLOCK.layout` and `packet_len` allow a future firmware (3.41,
  different packet size) without a new type code.
- Any copying tool (export of a session, spill import) must copy unknown
  types and unknown JSON fields verbatim.

## 15. Module map, public API and errors

```
python/sadi/store/
    failpoints.py    (DS2) failpoint(), configure()
    durable.py       (DS2) fsync_file, fsync_dir, create_exclusive, open_append,
                           rename_noreplace, atomic_replace, lock_file,
                           fs_warnings, free_space
    records.py       (DS3) frame encode/decode, type registry, payload models
    wal.py           (DS3) WalWriter, WalReader, ScanReport, WalConfig
    writer_thread.py (DS8) WriterHandle, WriterMetrics
    session.py       (DS4) create_session, resume_session, open_readonly, list_sessions
    manifest.py      (DS4) SessionManifestV1, write_manifest_cache, read_manifest_cache
    events.py        (DS5) replay(), PointV1, EditV1, MarkerV1 ... appliers
    snapshot.py      (DS5) write_snapshot, load_latest_snapshot, prefix_hash
    exports.py       (DS7) write_export, list_exports, ExportProvenanceV1
```

Signatures implementing tickets must match (typani `Result`; pydantic
frozen models for all records and reports):

```
# durable.py
def fsync_file(fd: int) -> Result[None, DurableError]
def fsync_dir(path: Path) -> Result[None, DurableError]
def create_exclusive(path: Path) -> Result[int, DurableError]
def open_append(path: Path) -> Result[int, DurableError]
def rename_noreplace(src: Path, dst: Path) -> Result[None, DurableError]
def atomic_replace(tmp: Path, dst: Path) -> Result[None, DurableError]
def lock_file(path: Path) -> Result[LockHandle, DurableError]
def fs_warnings(root: Path) -> list[StorageWarning]
def free_space(root: Path) -> Result[int, DurableError]

# wal.py
class WalWriter:
    def append_batch(self, records: Sequence[tuple[Seq, Record]]) -> Result[Seq, WalError]
    def rotate(self) -> Result[None, WalError]
    def close(self) -> Result[None, WalError]
class WalReader:
    @staticmethod
    def scan(version_dir: Path) -> Result[ScanReport, WalError]
    def records(self, from_seq: Seq = 1) -> Iterator[Result[Record, WalError]]

# writer_thread.py
class WriterHandle:
    def submit(self, record: Record) -> Result[Seq, StoreError]
    def wait_durable(self, seq: Seq, timeout_s: float) -> Result[None, StoreError]
    def metrics(self) -> WriterMetrics
    def close(self, timeout_s: float | None) -> Result[None, StoreError]

# session.py
def create_session(root: Path, meta: SessionCreate) -> Result[SessionHandle, SessionError]
def resume_session(parent_dir: Path) -> Result[SessionHandle, SessionError]
def open_readonly(version_dir: Path) -> Result[SessionView, SessionError]
def list_sessions(root: Path) -> Result[list[SessionListing], SessionError]

# snapshot.py / exports.py
def write_snapshot(session: SessionHandle, state: BaseModel, covers_seq: Seq) -> Result[Path, StoreError]
def load_latest_snapshot(view: SessionView) -> Result[SnapshotV1 | None, StoreError]
def write_export(session: SessionHandle, kind: str, basename: str, ext: str, payload: bytes, prov: ExportParams) -> Result[Path, StoreError]
```

Error taxonomy (frozen pydantic models or dataclasses per P2 conventions,
each with `hint: str` for the UI):

- `DurableError`: `Io(errno, path)`, `SharingViolation(path, attempts)`,
  `CrossDevice(tmp, dst)`, `Unsupported(op, reason)`, `Exists(path)`.
- `WalError`: `Torn(segment, offset, length)` (reported in `ScanReport`,
  not as `Err`), `Corrupt(segment, offset, reason)`,
  `UnsupportedFormat(found, supported)`, `SegmentHeaderInvalid(...)`,
  `Durable(DurableError)`.
- `SessionError`: `Locked(pid_hint)`, `ParentCorrupt(WalError)`,
  `DiskSpace(free, required)`, `NetworkFs(path, fstype)`,
  `TooManyVersions(family)`, `Incomplete(dir)`, `Wal(WalError)`,
  `Durable(DurableError)`.
- `StoreError`: `Backpressure(depth_bytes, waited_ms)`, `Stalled(seconds)`,
  `DiskFull(path, free)`, `IoError(DurableError)`, `Closed`,
  `Internal(repr)`, `Session(SessionError)`, `Wal(WalError)`.

Logging: module logger via `sadi.logging_setup.get_logger(__name__)`;
every state transition, every rotation, every fsync latency over 100 ms,
every retry, every failpoint hit and every error path is logged. `print`
is forbidden.

## 16. Open points and tickets to split off

Recommended new tickets (filed by the coordinator; DS1 does not widen its
scope for them):

1. Spill import at startup (6.5 step 4 and F23): scan spill locations and
   offer import as a new version. Depends on DS4; not in any DS ticket.
2. `sadi store` CLI: `verify <session>` (full scan incl. seal hashes),
   `prune-snapshots`, `regen-exports`, `info`. Depends on DS5/DS7.
3. docs/python-layout.md says the store lives under `sadi/core/store/`;
   the DS2-DS8 ticket scopes (and this doc) say `python/sadi/store/`.
   The layout doc should be corrected to match the tickets (docs fix).
4. The `crc32c` dependency must be added to `python/pyproject.toml` by DS3
   via lease widen; recorded here so P1's owner expects it.

Decisions deliberately left to CC1 ~DK06Q2F: exact queue hand-off between
the Rust acquisition thread (R8) and `WriterHandle.submit`, lock ordering
across the pipeline, and shutdown order of threads and the job pool.

Live-stream guard (audit2 H2b): `LiveAcquisition` additionally stops raw streaming at
`LIVE_MIN_FREE_BYTES = 1 GiB` free (before the writer's own 512 MiB warn level) and after an idle
timeout or session finish. Stopping drains all blocks already read into the WAL first and deletes
nothing; see docs/server/app.md.
