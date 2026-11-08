+++
id = "01M6WTCA3WJA26T204SWR6VW70"
title = "REST: export endpoints (CSV and figure data)"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T05:33:56Z"
updated = "2026-11-08T05:49:59Z"
scope = ["python/sadi/server/routes/export.py", "python/sadi/server/app.py", "python/tests/server/test_export_routes.py", "docs/server/export.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "REST: export endpoints (CSV and figure data)"
bound = true

[[acceptance]]
text = "GET /api/export lists formats; GET /api/export/{format} streams CSV with Content-Disposition and figure JSON inline"
bound = true
+++

found while working ~X3H80G2 (split out of its original acceptance). Use LabModule export_formats.
