+++
id = "01M6WVQWZ9WRFF3D09P2JB9SDC"
title = "Wire ResultsStream to JobManager sink and the WebSocket router"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T05:57:45Z"
updated = "2026-11-08T06:06:40Z"
scope = ["python/sadi/server/results_stream.py", "python/sadi/server/ws.py", "python/sadi/server/app.py", "python/tests/server/test_ws_results.py", "docs/server/results-stream.md", "docs/server/websocket.md"]

[[acceptance]]
text = "JobManager sink feeds ResultsStream: refining/final offered, stale ignored"
bound = true

[[acceptance]]
text = "WebSocket clients receive snapshot then live RESULTS_ENVELOPE frames with stale flag"
bound = true

[[acceptance]]
text = "Disconnect releases the stream connection"
bound = false
+++
