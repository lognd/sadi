+++
id = "01M6WWN90MKGKGY4H7Y8PWYEQZ"
title = "Stream live drift rate, capture-window raw seq and simulated flag"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T06:13:47Z"
updated = "2026-11-08T06:32:07Z"
scope = ["src/sadi/server/**", "python/sadi/server/ws.py", "python/sadi/server/app.py", "python/tests/server/test_ws.py", "web/src/ws/messages.ts", "web/src/ws/messages.test.ts", "web/src/screens/run/useRunLive.ts", "web/src/screens/run/live.ts", "docs/server/websocket.md", "docs/web/live-trace.md", "web/src/ws/ws.test.ts", "web/src/screens/run/RunScreen.test.tsx"]

[[acceptance]]
text = "State messages carry server drift_vps, capture-window first/last raw seq and a simulated flag (hello too); binary frames unchanged and documented"
bound = false

[[acceptance]]
text = "Web client parses and uses the streamed values"
bound = false
+++

found while working ~74FQXWT
