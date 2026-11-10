+++
id = "01M72BNYX112XQ7D2QJEAM66XT"
title = "Regenerate committed OpenAPI spec and TS types (stale after origin guard / audit4 routes)"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-10T09:12:30Z"
updated = "2026-11-10T09:13:58Z"
labels = ["audit4"]
scope = ["web/src/api/openapi.json", "web/src/api/schema.ts"]

[[acceptance]]
text = "test_committed_spec_not_stale passes; vitest api tests pass"
bound = true
+++
