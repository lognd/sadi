+++
id = "01M6X465ZVYG4B9Y79QAZ8KDXT"
title = "curve_source and notes() still walk the whole WAL per request"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T08:25:21Z"
updated = "2026-11-08T08:30:57Z"
scope = ["python/sadi/store/incremental.py", "python/sadi/server/curve_source.py", "python/sadi/server/service.py", "python/tests/store/test_incremental_notes.py", "python/tests/server/test_curve_notes_latency.py", "docs/store/incremental-replay.md", "docs/server/app.md"]

[[acceptance]]
text = "notes() and curve source tail the WAL incrementally, equal to a full scan, with equivalence and 200k-record latency tests"
bound = true
+++

found while working ~2RWJ137; same O(WAL) cost as _act had
