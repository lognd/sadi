+++
id = "01M6XAKF5AK7FCJNBHPM62NYRS"
title = "Run phase: give the live run a real phase owner instead of inferring it for WS guidance"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T10:17:28Z"
updated = "2026-11-08T10:23:15Z"
scope = ["docs/server/api.md", "docs/server/results.md", "python/sadi/server/routes/results.py", "python/sadi/server/routes/sessions.py", "python/sadi/server/run_phase.py", "python/sadi/server/schemas.py", "python/sadi/server/service.py", "python/tests/server/test_run_phase.py", "web/src/api/openapi.json"]

[[acceptance]]
text = "The live run's phase is owned by SessionService, advanced only through validated forward transitions recorded as append-only WAL markers; WS guidance reads it and infers only for sessions without a recorded phase"
bound = true
+++
