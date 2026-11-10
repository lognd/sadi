+++
id = "01M72854VNXD656XAJNYNKX6Y1"
title = "L6: WS loop does sync session-locked work on the event loop"
type = "bug"
category = "in-progress"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-10T08:10:53Z"
updated = "2026-11-10T08:13:13Z"
scope = ["python/sadi/server/ws.py", "docs/concurrency.md", "python/tests/server/test_ws_offloop.py"]

[[acceptance]]
text = "WS handler never blocks the event loop on session-locked work; test proves it"
bound = true
+++
