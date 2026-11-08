+++
id = "01M6WTCA1SET2XBYG05J73KJ11"
title = "REST: results, guidance and device status endpoints"
type = "task"
category = "in-progress"
priority = "medium"
points = 5
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T05:33:56Z"
updated = "2026-11-08T05:45:43Z"
scope = ["python/sadi/server/routes/results.py", "python/sadi/server/app.py", "python/tests/server/test_results_routes.py", "docs/server/results.md", "docs/server/app.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "REST: results, guidance and device status endpoints"
bound = true

[[acceptance]]
text = "GET /api/results, /api/results/budgets, /api/results/guidance and /api/device/status return typed bodies or problem+json with a hint"
bound = true
+++

found while working ~X3H80G2 (split out of its original acceptance). Live recompute results, guided-run guidance, device status.
