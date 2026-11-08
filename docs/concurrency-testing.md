# Concurrency testing: race, deadlock and kill-mid-write suite

Status: current

Parent: [concurrency.md](concurrency.md), [data-safety.md](data-safety.md).
Ticket: ~7B4SZGG. Code: `python/tests/concurrency/`.

## Scenarios

- `test_interleavings.py`: seeded storms over the deterministic job
  harness: capture during refinement, supersede storms, cancel storms,
  and trace replay. Each seed fixes the interleaving, so a failure is
  reproducible from its seed alone.
- `test_writer_races.py`: slow fsync with a full queue (backpressure,
  nothing acknowledged is lost), cancel during write, and writer lock
  order under contention.
- `test_kill_with_jobs.py`: SIGKILL of a subprocess mid-WAL-write while
  MC and GP jobs run (`external` kill by the parent, `self` kill via the
  `wal.write.partial` failpoint). Recovery must keep every acknowledged
  record, leave no torn state, and jobs restart from raw data.
- `test_shutdown_and_lag.py`: shutdown with live jobs terminates every
  worker; asyncio loop lag p99 stays under 50 ms with 50 kS/s
  acquisition and jobs active.

## Deadlock detection

`tracing.py` provides `TracedLock` and `LockTracer`, which enforce the
documented order L1 < L2 < L3 and raise on inversion, and
`run_with_deadline`, which dumps all thread stacks and fails on timeout.

## Knobs

- `SADI_CONC_SEEDS` (default 50): seeds per interleaving test.
- `SADI_CONC_KILL_SEEDS` (default 3): seeds per kill test mode.

## Why barriers, not sleeps

Synchronisation uses oracle lines ("ack N", "jobs_progressing",
"worker_pid N") and failpoints, never sleeps. The kill happens only after
jobs report progress, so the claim "killed while jobs run" is asserted,
not hoped for.
