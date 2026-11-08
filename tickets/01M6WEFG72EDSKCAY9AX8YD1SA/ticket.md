+++
id = "01M6WEFG72EDSKCAY9AX8YD1SA"
title = "store: data-directory lock so two sadi processes cannot share a data root"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 3
parent = "01M6W7R04QJTECCTSV9EY2JADK"
reporter = "lognd"
created = "2026-11-08T02:05:58Z"
updated = "2026-11-08T02:08:11Z"
idempotency_key = "sadi-store-lock"
labels = ["creates:python/sadi/store/lock.py", "creates:python/tests/store/test_lock.py", "creates:docs/store/lock.md"]
scope = ["python/sadi/store/lock.py", "python/tests/store/test_lock.py", "docs/store/lock.md", "docs/index.md"]

[[acceptance]]
text = "A second process opening the same data root gets a typed LockHeld error naming the holder pid; no data is touched"
bound = true

[[acceptance]]
text = "A stale lock from a dead pid is reported and recoverable only by explicit user action, never silently broken"
bound = true

[[acceptance]]
text = "Lock acquisition and release are logged; works on Linux, macOS and Windows (OS-level file lock, not pid-file only)"
bound = true
+++
