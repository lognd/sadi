# Write-ahead log

Status: current

Owner: ~4668M06. Code: `python/sadi/store/wal.py`, `python/sadi/store/records.py`.
Tests: `python/tests/store/test_wal.py`.
Design: [data-safety.md](../data-safety.md) sections 3-6, 9 and 11.

## Writer

`WalWriter.open(wal_dir, session_uuid, first_seq, config)` creates `seg-000001.wal`
exclusively, fsyncs file and directory, and starts one writer thread. Callers enqueue to a
bounded queue; only the thread touches the fd.

- `append(rec)` returns `Result[Seq, WalError]` after the record is durable (the documented
  durable gate). `append_nowait` returns at enqueue; `wait_durable(seq, timeout)` is the gate.
- Group commit has no timer: the thread drains up to 4 MiB or 1024 records per fsync.
- `durable_seq` is published only after `fsync` returns. fsync failure moves the writer to
  FAILED; undurable records stay in memory (`undurable_records()`).
- Rotation (256 MiB, or `rotate()`): SEAL record (takes the next seq, carries count and
  SHA-256 of the segment), fsync, create next segment, header, fsync, directory fsync.
  Rotation is decided at enqueue time so seal seqs stay dense.
- Failpoints: `wal.encode.before`, `wal.write.partial` (mid-batch), `wal.write.after`,
  `wal.fsync.before/after`, `wal.publish.after`, `wal.rotate.*`.

## CRC convention

CRC-32C (`crc32c` package) over the 32-byte frame header with the crc field zeroed,
followed by the payload. Segment header CRC covers bytes 0..59.

## Reader and recovery

`WalReader.scan(dir)` and `WalReader.records()` are read-only: nothing is ever truncated or
modified. Iteration stops at the verified prefix.

- Torn tail (partial or invalid last frame with no valid frame after it): `ScanReport.tail`
  gives segment, offset, length and SHA-256; the bytes stay on disk. Resume uses a new
  version directory.
- Anything else (bad CRC with valid frames after it, bad frame in a non-final segment, seq
  gap, segment gap, bad seal) is `Err(WalCorrupt)` carrying the verified prefix counts. It
  is never skipped.
- `ScanReport.prefix_hash` is SHA-256 over `seq u64 LE || crc u32 LE` per data record.

## Performance

`test_throughput_sustains_612_kbps_with_markers` writes 612 kB/s of RAW_BLOCK records plus
a marker every 50 blocks for 3 s, each append waiting for durability. Measured on the
WSL2 development laptop (ext4): **p99 append latency 9.5 ms, median 5.0 ms**. Latency is
dominated by one fsync per append at this low rate; the test asserts p99 < 250 ms.
Real-disk numbers vary; rerun with `pytest -s` to see them.

## Observers

`set_fsync_observer(fn)` receives each fsync latency in ms; `set_failure_observer(fn)`
receives the `WalError` when the writer enters FAILED. Both run outside the WAL lock and
exceptions are logged, not raised. See [writer-thread.md](writer-thread.md).
