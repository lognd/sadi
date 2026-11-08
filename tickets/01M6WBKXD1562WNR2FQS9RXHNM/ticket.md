+++
id = "01M6WBKXD1562WNR2FQS9RXHNM"
title = "Add Backpressure/DiskFull/Closed/Stalled to StoreCode"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T01:15:57Z"
updated = "2026-11-08T03:26:15Z"
scope = ["python/sadi/core/errors.py", "python/tests/core/test_models.py", "docs/data-safety.md"]
+++

found while working ~3F2W55E; writer_thread.py defines these errors locally
