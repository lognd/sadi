+++
id = "01M6X8XTQ31XRDC5BZFNQZXN6Q"
title = "Plots and export routes reuse IncrementalReplay instead of walking the whole WAL"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T09:48:10Z"
updated = "2026-11-08T09:55:54Z"
scope = ["docs/server/*.md", "python/sadi/server/*.py", "python/sadi/server/routes/*.py", "python/tests/server/test_session_replay_cache.py"]

[[acceptance]]
text = "Plots and export routes reuse the shared IncrementalReplay cache with full-replay fallback"
bound = true
+++
