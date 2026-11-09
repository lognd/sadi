+++
id = "01M6Z4H8GRP83B32G68N220D8K"
title = "doctor WEB-010/DATA-010: actionable setup steps (build UI bundle, create data root) and sadi doctor fix --apply entries"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:09:53Z"
updated = "2026-11-09T03:15:32Z"
idempotency_key = "web010-data010-steps"
scope = ["python/sadi/doctor/checks/web.py", "python/sadi/doctor/checks/data.py", "python/sadi/doctor/probes.py", "python/tests/doctor/test_web_data_steps.py", "docs/doctor-checks.md"]

[[acceptance]]
text = "WEB-010 and DATA-010 remediation give concrete, read-only-safe setup commands"
bound = true
+++
