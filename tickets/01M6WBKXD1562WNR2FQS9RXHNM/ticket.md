+++
id = "01M6WBKXD1562WNR2FQS9RXHNM"
title = "Add Backpressure/DiskFull/Closed/Stalled to StoreCode"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T01:15:57Z"
updated = "2026-11-08T03:26:40Z"
scope = ["python/sadi/core/errors.py", "python/tests/core/test_models.py", "docs/data-safety.md"]

[[acceptance]]
text = "StoreCode has backpressure, disk_full, closed and stalled, each with a hint and problem body"
bound = true
+++

found while working ~3F2W55E; writer_thread.py defines these errors locally
