+++
id = "01M6XBHBQBE3XM2A685QGTY599"
title = "WorkerSlot.join races the pump thread's own proc.join"
type = "bug"
category = "todo"
priority = "medium"
reporter = "lognd"
created = "2026-11-08T10:33:47Z"
updated = "2026-11-08T10:33:47Z"
scope = ["python/sadi/jobs/pool.py"]
+++

found while working ~AKSBJQ6: after the pump reaps the child, join() can return False for a politely exited worker.
