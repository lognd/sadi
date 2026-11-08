# Sessions

Status: current

Owner: ~GCJAR1J. Code: `python/sadi/store/session.py`, `python/sadi/store/manifest.py`.
Tests: `python/tests/store/test_session.py`.
Design: [data-safety.md](../data-safety.md) section 8; WAL: [wal.md](wal.md).

## Create

`create_session(root, meta)` makes `<root>/sessions/<UTC stamp>-<slug>.v001` with
`os.mkdir` (exclusive). `FileExistsError` moves to the next version; a directory is never
reused, deleted or `exist_ok`'d. After 999 versions the result is `TooManyVersions`.
Then `wal/`, `snapshots/`, `exports/`, the lock, the manifest, and fsync of the session
directory and `sessions/`. A crash at any step leaves at most an `incomplete` directory that
is skipped; the next create takes a new version.

Not done here: writing `SESSION_START` through the WAL writer (pipeline ticket).

## Resume

`resume_session(parent_dir)` refuses a locked, WAL-less (`ParentIncomplete`) or corrupt
(`ParentCorrupt`) parent, scans the parent read-only, and creates the next version with
`parent` and `parent_last_seq` in its manifest. The parent, including a torn tail, is never
touched.

## Manifest

`Manifest` is a frozen pydantic model, a derived cache (losable). `write_manifest` creates
`manifest.json.tmp-<pid>-<rand>` exclusively, fsyncs it, then `atomic_replace`.
Failpoints: `session.manifest.write`, `session.manifest.before_replace`.

## Lock

File `lock` is created exclusively and never deleted. The writer holds an OS process-scoped
lock (POSIX `flock`, Windows `msvcrt.locking` byte 0), so the kernel releases it on death and
a lock is stale exactly when it can be acquired. A live lock is never stolen: `probe_lock`
returns `Locked` with the holder line (`pid=.. start=.. host=..`). `read_lock_holder`
judges holder liveness from pid plus process start-time token (`/proc` on Linux, `ps` on
macOS, `GetProcessTimes` on Windows), which also detects pid reuse. Windows and macOS paths
are untested on CI here.

## Read-only open

`open_readonly(dir)` reads manifest, the lock text and scans the WAL; it takes no lock and
writes nothing, not even to repair a stale manifest (it reports `manifest_stale`). Tests
hash the whole tree (names, sizes, mtimes, bytes) before and after.

Failpoints: `session.mkdir.before`, `session.lock.after`.

Command line: [cli.md](cli.md).

## Spill import

Emergency spill files from a forced quit are imported as a new version at start; see
[spill.md](spill.md).
