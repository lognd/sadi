+++
id = "01M724E09H9X4DDW9ATK14JQ5C"
title = "Wire LiveAcquisition.finish() into results/export and show stop_reason/fault in the UI"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T07:05:50Z"
updated = "2026-11-10T07:29:00Z"
labels = ["creates:python/tests/server/test_finish_wiring.py"]
scope = ["python/sadi/server/service.py", "python/sadi/server/routes/results.py", "python/tests/server/test_finish_wiring.py", "python/sadi/server/app.py", "python/sadi/server/routes/export.py", "python/tests/server/test_results_routes.py", "web/src/api/openapi.json", "web/src/api/schema.ts", "web/src/components/instrument/useBackendFacts.ts", "docs/server/app.md", "docs/server/results.md", "changelog.d/01M724E09H9X4DDW9ATK14JQ5C.fixed.md"]

[[acceptance]]
text = "Reaching Results/Export (or closing the session) calls finish(); the health/status API exposes stop_reason and fault; test asserts no raw blocks after finish"
bound = true
+++
