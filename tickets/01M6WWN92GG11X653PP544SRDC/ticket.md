+++
id = "01M6WWN92GG11X653PP544SRDC"
title = "Endpoint for per-phase plot data (calibration, stress-strain)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T06:13:47Z"
updated = "2026-11-08T06:28:26Z"
scope = ["src/sadi/server/**", "python/sadi/server/routes/plots.py", "python/tests/server/test_plots_routes.py", "docs/server/plots.md", "docs/server/api.md", "docs/server/export.md", "python/sadi/server/app.py", "web/src/api/openapi.json", "web/src/api/schema.ts"]

[[acceptance]]
text = "GET /api/plots/calibration returns points plus fit line and 95% band (fit null below 3 points)"
bound = true

[[acceptance]]
text = "GET /api/plots/stress-strain returns strain, MPa stress and excluded flags, read-only"
bound = true

[[acceptance]]
text = "No open session yields 409 problem+json with a hint"
bound = true
+++

found while working ~74FQXWT
