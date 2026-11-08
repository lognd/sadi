+++
id = "01M6WA9WZW89EA826DSJCJ0197"
title = "Doctor UI screen: show checks and guided fix steps in the web app"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T00:53:00Z"
updated = "2026-11-08T03:33:17Z"
labels = ["model:sonnet", "ws:web"]
scope = ["web/src/doctor/**", "web/src/api/client.ts", "web/src/api/schema.ts", "web/src/App.tsx"]

[[links]]
kind = "blocked-by"
target = "01M6WA9WYE9D71BBA7AV3H5CGF"

[[acceptance]]
text = "Doctor screen lists checks with status and expandable numbered fix steps, re-run per check"
bound = false

[[acceptance]]
text = "Reachable from any wizard step and from device-connection errors"
bound = false
+++
