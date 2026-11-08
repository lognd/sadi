+++
id = "01M6X9NXWB7KW3ZGQP02KDWN8N"
title = "WS guidance message carries no payload; define pydantic model and show in UI"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T10:01:20Z"
updated = "2026-11-08T10:06:14Z"
scope = ["web/src/screens/run/useRunLive.ts", "web/src/screens/run/RunScreen.tsx", "web/src/screens/run/RunScreen.test.tsx", "docs/server/websocket.md", "python/sadi/server/ws.py"]

[[acceptance]]
text = "WS guidance message carries a frozen extra=forbid pydantic payload (phase, next_action, stop_early, stop_reason); web parses it and RunScreen shows next_action; pytest and vitest cover it"
bound = false
+++
