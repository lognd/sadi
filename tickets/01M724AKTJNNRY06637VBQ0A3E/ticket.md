+++
id = "01M724AKTJNNRY06637VBQ0A3E"
title = "Audit2 H8b: read-only export of closed sessions with a Download button"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T07:03:59Z"
updated = "2026-11-10T07:19:01Z"
labels = ["creates:python/tests/server/test_readonly_export.py"]
scope = ["python/sadi/server/routes/export.py", "python/sadi/server/routes/sessions.py", "web/src/screens/setup/SessionSetup.tsx", "web/src/screens/setup/sessionApi.ts", "python/tests/server/test_readonly_export.py", "web/src/screens/export/api.ts", "web/src/screens/setup/SessionSetup.test.tsx", "docs/server/export.md", "docs/web/export-screen.md", "changelog.d/01M724AKTJNNRY06637VBQ0A3E.changed.md", "python/sadi/server/service.py", "web/src/api/openapi.json", "web/src/api/schema.ts"]

[[acceptance]]
text = "GET /api/sessions/{name}/export/{fmt} returns the CSV for a closed session without creating a version or writing to the session; SessionSetup shows a Download button per closed session; works with no board attached"
bound = true
+++
