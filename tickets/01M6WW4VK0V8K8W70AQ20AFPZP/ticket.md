+++
id = "01M6WW4VK0V8K8W70AQ20AFPZP"
title = "Regenerate web/src/api/schema.ts (openapi-typescript) so provenance appears; drop hand mirror in export/types.ts"
type = "task"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T06:04:49Z"
updated = "2026-11-08T06:07:13Z"
scope = ["web/src/api/schema.ts", "web/src/api/openapi.json", "web/src/screens/export/types.ts"]

[[acceptance]]
text = "schema.ts contains QuantityProvenance and provenance (schema drift test passes)"
bound = true

[[acceptance]]
text = "export/types.ts uses the generated QuantityProvenance type"
bound = true
+++
