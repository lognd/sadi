+++
id = "01M727MMWZ8X2B29300XHTWZ46"
title = "Web: Resume live readings button calling POST /api/acquisition/resume"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T08:01:53Z"
updated = "2026-11-10T08:08:59Z"
scope = ["web/src/components/instrument/StopBanner.tsx", "web/src/components/instrument/StopBanner.test.tsx", "web/src/api/client.ts"]

[[acceptance]]
text = "idle stop banner shows a Resume live readings button posting /api/acquisition/resume, disabled while pending, shows 409 hint; vitest tests"
bound = true
+++
