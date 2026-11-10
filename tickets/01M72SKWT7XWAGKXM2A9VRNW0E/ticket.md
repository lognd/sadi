+++
id = "01M72SKWT7XWAGKXM2A9VRNW0E"
title = "Regenerate web/src/api/schema.ts: missing SessionSummary.spill_import"
type = "bug"
category = "todo"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-10T13:16:03Z"
updated = "2026-11-10T13:16:03Z"
labels = ["creates:none"]
scope = ["web/src/api/schema.ts"]

[[acceptance]]
text = "schema.ts contains spill_import on SessionSummary and matches openapi.json (npm run gen:ts); tsc --noEmit clean"
bound = false
+++
