+++
id = "01M6XBHBQBE3XM2A685QGTY599"
title = "WorkerSlot.join races the pump thread's own proc.join"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T10:33:47Z"
updated = "2026-11-08T10:36:35Z"
scope = ["python/sadi/jobs/pool.py", "python/tests/jobs/test_pool_slot.py", "changelog.d/*QGTY599*"]

[[acceptance]]
text = "WorkerSlot.join returns True for a worker that exited politely; regression test covers the race"
bound = true
+++

found while working ~AKSBJQ6: after the pump reaps the child, join() can return False for a politely exited worker.
