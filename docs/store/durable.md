# Store durability primitives

Status: current

Owner: ~JA5DMTN. Code: `python/sadi/store/durable.py`, `python/sadi/store/failpoints.py`.
Tests: `python/tests/store/test_durable.py`, `python/tests/store/test_failpoints.py`.
Design: [data-safety.md](../data-safety.md) sections 10 and 11 (followed exactly).

All fallible calls return typani `Result[T, DurableError]`; errors are frozen pydantic
models (`DurableIo`, `DurableSharingViolation`, `DurableCrossDevice`, `DurableUnsupported`,
`DurableExists`), each with a UI `hint`.

## API

- `fsync_file(fd)`: `os.fsync` (never `fdatasync`); on macOS `F_FULLFSYNC` with a
  once-logged fallback to `fsync` on `ENOTSUP`/`EINVAL` (see `durability_downgraded()`).
  On Windows `os.fsync` maps to `FlushFileBuffers`.
- `fsync_dir(path)`: opens the directory and flushes it. On Windows it calls
  `CreateFileW(..., FILE_FLAG_BACKUP_SEMANTICS)` then `FlushFileBuffers` via ctypes
  (`_win_flush_dir`); failures are logged at ERROR and returned as `DurableIo`.
  **UNVERIFIED: the Windows path has not been run on Windows.**
- `create_exclusive(path)`: `O_CREAT|O_EXCL` (`CREATE_NEW` on Windows, `O_BINARY` set).
  An existing file yields `DurableExists` and is never touched.
- `atomic_replace(tmp, dst)`: refuses if `tmp` and `dst` have different parents
  (`DurableCrossDevice`), fsyncs `tmp`, renames (`os.replace`, or `MoveFileExW` with
  `REPLACE_EXISTING|WRITE_THROUGH` on Windows), then `fsync_dir`. On any failure before the
  rename `dst` is unchanged. Derived files only (invariant I4); callers ensure the new
  content is a superset of the old.
- `rename_noreplace(src, dst)`: renames without ever replacing `dst`; an existing `dst`
  yields `DurableExists` and both files are untouched. Linux: `renameat2(RENAME_NOREPLACE)`
  via ctypes, falling back to link+unlink when the kernel or filesystem returns
  `ENOSYS`/`EINVAL`/`ENOTSUP`. Windows: `MoveFileExW` with `WRITE_THROUGH` and without
  `REPLACE_EXISTING` (`ERROR_FILE_EXISTS`/`ERROR_ALREADY_EXISTS` map to `DurableExists`),
  with the sharing-violation retry. macOS and other OSes: `os.link` then `os.unlink`
  (a crash between the two leaves both names; recovery must tolerate it). Afterwards the
  destination (and a different source) directory is fsynced. **UNVERIFIED: Windows and
  macOS paths have not been run on those OSes**; Windows is exercised only with a faked
  `MoveFileExW`, macOS only through the link+unlink fallback on Linux.
- Windows sharing-violation retry (`winerror` 5 or 32): backoff 10 ms doubling, capped at
  500 ms, 5 s total, then `DurableSharingViolation`. Each retry logs at WARNING.

## Failpoints

`failpoints.failpoint(name)` is a cheap no-op unless armed via `SADI_FAILPOINTS`
(`name=action,...`) or `failpoints.configure({...})`. Actions: `kill`, `abort`,
`sleep:<ms>`, `error:<errno>`, with `once:`, `nth:<n>:` and `prob:<p>:` prefixes. The
primitives hit `durable.fsync_file` (flushes) and `durable.rename` (rename/replace/create).
The `durable.write` point belongs to the WAL write loop and is not placed here.

## Not yet implemented

`open_append`, `lock_file`, `fs_warnings`, `free_space` (other tickets).
