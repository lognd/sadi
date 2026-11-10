+++
id = "01M72YAG3BHTR584JK3TY2DE40"
title = "Every page load runs the full doctor (~24 s) to learn the data folder (audit8 M1)"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T14:38:18Z"
updated = "2026-11-10T14:44:25Z"
scope = ["python/sadi/server/routes/**", "python/sadi/server/routes_health.py", "python/sadi/server/app.py", "python/tests/server/test_routes_health.py", "web/src/api/client.ts", "web/src/components/instrument/useBackendFacts.ts"]

[[acceptance]]
text = "Data folder lookup does not run the full doctor."
bound = true
+++

See /tmp/claude-1000/-home-logan-projects-SADI/4f193782-dc1d-4c66-a170-89d2ce998f4d/scratchpad/audit8.md section M1.
