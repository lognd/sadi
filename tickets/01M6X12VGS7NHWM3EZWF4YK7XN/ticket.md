+++
id = "01M6X12VGS7NHWM3EZWF4YK7XN"
title = "launcher: wire live acquisition bus so /api/stream is mounted (e2e readout stays stale)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-08T07:31:06Z"
updated = "2026-11-08T07:38:36Z"
scope = ["python/sadi/server/live.py"]

[[acceptance]]
text = "A sim launcher serves WS /api/stream and live frames reach the browser readout; samples still flow through the session WAL"
bound = false
+++
