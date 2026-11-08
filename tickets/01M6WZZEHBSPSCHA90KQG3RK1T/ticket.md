+++
id = "01M6WZZEHBSPSCHA90KQG3RK1T"
title = "Backend: add GET /api/health route the web client calls"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T07:11:46Z"
updated = "2026-11-08T07:18:36Z"
scope = ["creates:python/sadi/server/routes_health.py", "creates:python/tests/server/test_routes_health.py", "python/sadi/server/app.py", "docs/server/app.md", "web/src/api/openapi.json", "python/sadi/server/routes_health.py", "python/tests/server/test_routes_health.py", "changelog.d/01M6WZZEHBSPSCHA90KQG3RK1T.fixed.md"]

[[acceptance]]
text = "GET /api/health returns 200 {status, version} with no session"
bound = true
+++
