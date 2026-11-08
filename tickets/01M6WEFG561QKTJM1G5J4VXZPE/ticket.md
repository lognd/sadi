+++
id = "01M6WEFG561QKTJM1G5J4VXZPE"
title = "durable: no-replace rename primitive and Windows directory flush (ctypes)"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R04QJTECCTSV9EY2JADK"
reporter = "lognd"
created = "2026-11-08T02:05:58Z"
updated = "2026-11-08T02:08:14Z"
idempotency_key = "sadi-durable-noreplace"
scope = ["python/sadi/store/durable.py", "python/tests/store/test_durable*.py", "docs/store/durable.md", "docs/data-safety.md"]

[[acceptance]]
text = "rename_noreplace(src, dst) fails with a typed Result error when dst exists, using renameat2(RENAME_NOREPLACE) on Linux, MoveFileExW without REPLACE_EXISTING on Windows, link+unlink fallback on macOS"
bound = true

[[acceptance]]
text = "fsync_dir on Windows flushes the directory handle via ctypes (FlushFileBuffers on a FILE_FLAG_BACKUP_SEMANTICS handle) instead of a no-op, with the failure path logged"
bound = true

[[acceptance]]
text = "docs/store/durable.md and data-safety.md section 10 updated; Windows and macOS paths marked UNVERIFIED until run on those OSes"
bound = true
+++
