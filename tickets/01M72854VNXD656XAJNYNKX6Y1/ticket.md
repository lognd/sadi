+++
id = "01M72854VNXD656XAJNYNKX6Y1"
title = "L6: WS loop does sync session-locked work on the event loop"
type = "bug"
category = "in-progress"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-10T08:10:53Z"
updated = "2026-11-10T08:12:30Z"
scope = ["python/sadi/server/ws.py", "docs/concurrency.md"]

[[acceptance]]
text = "WS handler never blocks the event loop on session-locked work; test proves it"
bound = false
+++
