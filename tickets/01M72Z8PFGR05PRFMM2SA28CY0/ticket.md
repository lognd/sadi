+++
id = "01M72Z8PFGR05PRFMM2SA28CY0"
title = "Faulted device still reads Connected; backend simulated flag derives from status"
type = "bug"
category = "todo"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T14:54:47Z"
updated = "2026-11-10T14:54:47Z"
scope = ["web/src/screens/run/**", "python/sadi/server/app.py"]

[[acceptance]]
text = "A faulted device is shown as faulted, not Connected, and the simulated flag survives a fault on the backend."
bound = false
+++

Leftover from ~2KP8YNY: app.py derives simulated from status == simulated; source word can read Simulated or Connected on a faulted device.
