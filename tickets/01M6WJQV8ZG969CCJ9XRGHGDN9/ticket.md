+++
id = "01M6WJQV8ZG969CCJ9XRGHGDN9"
title = "WAL scan errors on a torn first segment header (zero acks); treat as empty"
type = "bug"
category = "in-progress"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-08T03:20:26Z"
updated = "2026-11-08T03:43:35Z"
scope = ["python/sadi/store/wal.py", "python/tests/store/test_wal.py", "docs/data-safety.md"]

[[acceptance]]
text = "A lone first segment with a short magic-prefix header scans Ok as empty with a torn-tail record, file untouched"
bound = true

[[acceptance]]
text = "A full-length corrupt or non-magic first header still returns Err"
bound = false
+++
