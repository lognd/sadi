+++
id = "01M727YGXCC6ZFVHWHG64KFA7D"
title = "L1+L2: results/finish never called by UI and docs claim it; export filename ignores server name and fails silently"
type = "bug"
category = "in-progress"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-10T08:07:17Z"
updated = "2026-11-10T08:07:33Z"
scope = ["docs/server/results.md", "web/src/screens/run/exportTrace.ts", "web/src/screens/WizardHost.tsx"]

[[acceptance]]
text = "Docs match actual UI behavior; F3 export uses server-provided filename; export failure shows a visible error"
bound = false
+++
