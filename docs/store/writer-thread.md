# WAL writer thread

Status: current

Owner: ~3F2W55E. Code: `python/sadi/store/writer_thread.py`, `python/sadi/store/wal.py`.
Tests: `python/tests/store/test_writer_thread.py`.
Design: [data-safety.md](../data-safety.md) section 7, [concurrency.md](../concurrency.md).

`WriterHandle` is the thread-safe facade acquisition code uses. The WAL's dedicated
thread (`sadi-wal-writer`, see [wal.md](wal.md)) owns the file; fsync never runs on a
producer thread.

## Backpressure, never loss

`submit(record)` returns `Result[Seq, WriterError]`. When the bounded queue stays full
past `submit_timeout_s` it returns `Backpressure` and assigns no seq; the caller still
holds the record and decides to retry or stop. Accepted records are never dropped.

## Metrics

`metrics()` returns a pydantic `WriterMetrics`: state, queue depth (items, bytes),
`enqueued_seq`, `durable_seq`, fsync latency (count, last, p50, p99), submit wait,
`backpressure_events`, segment info, free disk bytes and the stored error.

## Durability and shutdown

`durable_seq` is published monotonically. `close(final)` enqueues an optional final
record, drains the queue, fsyncs and joins; it is idempotent. Later submits return
`Closed`.

## Failure

A write or fsync error moves the writer to FAILED. ENOSPC maps to `DiskFull`, other
errnos to `IoError`. Waiters, `check_health()`, later `submit` calls and registered
`on_failure` listeners all receive the typed error. Unflushed records stay in memory
(`undurable_count()`). No durable progress for `stall_timeout_s` (5 s) while records are
outstanding yields `Stalled` from `check_health()`; it clears when `durable_seq` advances.

## Observer hooks

`WalWriter.set_fsync_observer` and `set_failure_observer` feed per-fsync latency and
failure notifications to the handle; observers run outside the WAL lock.
