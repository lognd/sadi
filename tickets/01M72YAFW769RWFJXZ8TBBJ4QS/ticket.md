+++
id = "01M72YAFW769RWFJXZ8TBBJ4QS"
title = "Frozen retry body outlives refusals that wrote nothing; later Accept saves stale data (audit8 M2)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T14:38:17Z"
updated = "2026-11-10T15:00:09Z"
scope = ["python/sadi/server/capture.py", "web/src/screens/run/live.ts", "web/src/screens/run/capture.ts"]

[[acceptance]]
text = "A refusal that wrote nothing clears the frozen retry body."
bound = false
+++

See /tmp/claude-1000/-home-logan-projects-SADI/4f193782-dc1d-4c66-a170-89d2ce998f4d/scratchpad/audit8.md section M2.
