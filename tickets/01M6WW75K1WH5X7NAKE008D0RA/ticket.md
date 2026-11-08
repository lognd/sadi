+++
id = "01M6WW75K1WH5X7NAKE008D0RA"
title = "Results-stream Subscribe adapter over WS /api/stream (RESULTS_ENVELOPE frames)"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T06:06:05Z"
updated = "2026-11-08T06:09:04Z"
scope = ["web/src/results-stream/wsSubscribe.ts", "web/src/results-stream/wsSubscribe.test.ts", "web/src/results-stream/index.ts", "docs/web/results-stream.md"]

[[acceptance]]
text = "wsSubscribe forwards only RESULTS_ENVELOPE frame bodies from WS /api/stream"
bound = false

[[acceptance]]
text = "reconnect replays never regress state and unsubscribe closes the socket"
bound = false
+++
