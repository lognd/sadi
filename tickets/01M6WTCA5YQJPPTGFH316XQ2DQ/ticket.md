+++
id = "01M6WTCA5YQJPPTGFH316XQ2DQ"
title = "Publish OpenAPI and generate TypeScript client into web/src/api"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T05:33:56Z"
updated = "2026-11-08T05:58:04Z"
scope = ["web/src/api/**", "python/sadi/server/openapi_export.py", "python/tests/server/test_openapi_export.py", "web/package.json", "web/src/api/schema.test.ts", "docs/web-api-client.md", "changelog.d/01M6W7R0KH8QFP4K9PTM197V9E.changed.md", "changelog.d/01M6W7R0PMCGFDSFY53XDK2EVN.changed.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "Publish OpenAPI and generate TypeScript client into web/src/api"
bound = false
+++

found while working ~X3H80G2 (split out of its original acceptance). Generated client must be drift-checked.
