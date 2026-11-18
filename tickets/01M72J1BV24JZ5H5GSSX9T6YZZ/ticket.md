+++
id = "01M72J1BV24JZ5H5GSSX9T6YZZ"
title = "Hanging server tests: test_loop_lag handlers_respond_while_job_runs and *latency* tests stall"
type = "bug"
category = "todo"
priority = "medium"
reporter = "lognd"
created = "2026-11-10T11:03:35Z"
updated = "2026-11-10T11:03:35Z"
idempotency_key = "hang-loop-lag-2026-11-10"
labels = ["tests"]
scope = ["python/tests/server/test_loop_lag.py", "python/tests/server/test_action_latency.py", "python/tests/server/test_curve_notes_latency.py"]

[[acceptance]]
text = "test_loop_lag.py::test_handlers_respond_while_job_runs passes within 60s on main in isolation; the two latency tests pass reliably under a full tests/server run"
bound = false
+++
