+++
id = "01M72VV7AGMWE3JE4MZFA8P5T6"
title = "Replay fallback must compare request digest; OpenAPI declares capture 409/503 and design reason enum"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T13:55:00Z"
updated = "2026-11-10T14:06:46Z"
scope = ["python/sadi/server/service.py", "python/sadi/server/routes/sessions.py", "python/sadi/server/schemas*.py", "web/src/api/**", "python/tests/server/test_capture_request_id.py", "python/sadi/store/events.py", "python/sadi/design/models.py", "python/sadi/design/selector.py", "python/sadi/server/routes/design.py", "python/tests/server/test_openapi_export.py", "docs/server/app.md", "changelog.d/01M72VV7AGMWE3JE4MZFA8P5T6.fixed.md"]

[[acceptance]]
text = "Fallback replay path through stored points compares the narrowed digest and returns 409 on mismatch; POST /api/session/points declares 409 and 503 ApiProblem responses; DesignIndicator reasons are an enum; openapi.json and schema.ts regenerated"
bound = false
+++

Audit7 L4, L7. Start only after ~DYDN79W lands (same files).
