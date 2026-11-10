+++
id = "01M71Z6EMJ9QP7716699S5SC5X"
title = "Audit1 #5 #23 #40: stale lock guidance, SO_REUSEADDR port check, unwritable root hint"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T05:34:19Z"
updated = "2026-11-10T05:40:27Z"
scope = ["python/sadi/store/lock.py", "python/tests/cli/**", "python/tests/store/test_lock*.py", "python/sadi/launcher.py", "docs/server/launcher.md", "docs/data-safety.md"]

[[acceptance]]
text = "Stale lock after crash has a plain recovery path without data loss, port check uses SO_REUSEADDR, unwritable root hint shown; tests added"
bound = true
+++
