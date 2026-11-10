+++
id = "01M7279606J0ZW8ZY1RZG2ZHS9"
title = "M3+M7: resume endpoint after idle pause; keep raw blocks when stop/reconnect fails"
type = "bug"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T07:55:37Z"
updated = "2026-11-10T08:00:02Z"
labels = ["creates:python/tests/server/test_resume_and_stop_keep.py"]
scope = ["python/sadi/server/live.py", "python/sadi/core/device.py", "python/sadi/api/acquisition.py", "python/sadi/server/routes/acquisition.py", "python/sadi/server/app.py", "docs/server/api.md", "python/tests/**"]

[[acceptance]]
text = "POST /api/acquisition/resume restarts streaming without writing a load-change marker; stop_streaming returns drained pending blocks even on stop error and they are ingested before the fault is reported; Reconnect teardown keeps pending blocks; tests"
bound = true
+++
