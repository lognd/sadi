# Data-root lock

Status: current

Owner: ~X8YD1SA. Code: `python/sadi/store/lock.py`. Tests: `python/tests/store/test_lock.py`.
Design: [data-safety.md](../data-safety.md); sessions: [session.md](session.md).

`acquire(root)` returns `Result[DataRootLock, LockError]`. It takes a non-blocking exclusive
OS lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) on `<root>/.sadi-data.lock` and
writes `pid=<pid> host=<host>` into it. The OS drops the lock when the process dies, so a
pid file alone is never trusted.

- Held by a live process: `LockHeld(pid=...)`. Nothing else is touched.
- OS lock free but the file still names a pid (an unclean exit; `release` truncates the file):
  `LockStale(pid=...)`. It is reported and never broken silently; the caller must retry with
  `acquire(root, recover_stale=True)` as an explicit user action.
- OS failures: `LockIo(errno=...)`.

Acquire, release, held and stale events are logged. The lock file is never deleted.

## Callers

- `create_session(root, meta, now, *, recover_stale=False)` and
  `resume_session(parent_dir, *, recover_stale=False)` in `python/sadi/store/session.py`
  take the lock first (for resume the root is `parent_dir/../..`), before any session dir is
  created. `SessionHandle` holds the `DataRootLock` for the session's lifetime; `close()`
  releases it after the manifest is written. If session creation fails the lock is released.
- Failures surface as `Err(RootLockFailed(error=LockHeld | LockStale | LockIo))` in the
  `SessionError` family; nothing is raised. A second open of the same root, even in the same
  process, yields `LockHeld` with the recorded pid and touches no session data.
- `LockStale` is returned to the caller; only an explicit `recover_stale=True` retry (a user
  choice) takes the lock over. Read-only open (`open_readonly`) never locks.
- Not yet wired: the CLI (`sadi.cli.store.cmd_recover`) shows `RootLockFailed` through its
  generic message, and no launcher startup path calls `acquire` yet.

## Verification status

Linux is tested (including a two-process test). The Windows (`msvcrt.locking`, `OpenProcess`
liveness) and macOS paths are UNVERIFIED: written to the same interface but not run here.
