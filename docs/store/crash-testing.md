# Crash-recovery testing

Status: current

Owner: ~HAH4MTB. Code: `python/tests/crash/` (`crashee.py`, `harness.py`, `test_crash.py`).
CI: `.github/workflows/crash.yml`. Design: [data-safety.md](../data-safety.md) sections 1 and 12;
WAL: [wal.md](wal.md); sessions: [session.md](session.md); lock: [lock.md](lock.md).

## What it does

`crashee.py` is a writer subprocess. It creates a session, opens a `WalWriter` and appends
deterministic records in batches, writing snapshots and manifest updates along the way. Every
acknowledged seq, committed snapshot (with sha256) and post-fsync segment size goes to an
append-only oracle log with one `os.write` per line. The harness kills it and reopens the data
root; the oracle says what was promised, the disk says what survived.

Kill modes:

- Randomized: `Popen.kill()` after a random delay (SIGKILL on POSIX, TerminateProcess on Windows).
- Failpoint: `SADI_FAILPOINTS=<name>=nth:K:kill` makes the child `os._exit(137)` at an exact
  step (session mkdir, lock, manifest write/replace, WAL encode/write/partial/fsync/publish,
  segment rotation, snapshot write/rename/dirsync, durable write/fsync/rename).
- Power loss: the last WAL segment of a copy is truncated to the last fsynced offset plus
  0-4096 random bytes, emulating un-fsynced data that never reached the disk.

Seeds alternate tiny segments (constant rotation) and one large segment.

## Invariants checked after every kill

- I1/I2: recovered records are a gapless prefix (SEAL seqs excepted) and include every ack.
- I3: no corrupt record accepted; every RAW_BLOCK payload equals the generator output.
- I4/I5: committed snapshots are unchanged; no torn snapshot at a final path; latest snapshot
  loads (old or new, never partial).
- I7/I10: replay is deterministic and snapshot-assisted recovery equals full replay.
- Recovery does not modify the session dir (tree digest unchanged), no session is overwritten,
  and a stale data-root lock is refused until `recover_stale=True`.

## Running

    cd python
    uv run pytest tests/crash                       # quick: 8 random, 4 power-loss, 1 sweep
    SADI_CRASH_ITERATIONS=200 uv run pytest tests/crash
    SADI_CRASH_ARTIFACTS=/tmp/crash-art uv run pytest tests/crash   # keep failing sessions

`SADI_CRASH_FP_RUNS` repeats the failpoint sweep. CI sets ITERATIONS=200 on ubuntu, windows and
macos and uploads `crash-artifacts` (session root plus oracle log) when any run fails.

## Known gaps

- A torn first segment header with zero acks is tolerated; the scan error is ~RGHGDN9.
- Exports are not covered.
