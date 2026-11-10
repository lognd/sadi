+++
id = "01M72964B6QESNJ271PXD2H2RQ"
title = "audit4 L1+L2+L6: idle-pause capture hint wrong, resume ignores device health, SETTINGS firmware always null"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T08:28:55Z"
updated = "2026-11-10T08:31:52Z"
labels = ["audit4"]
scope = ["python/sadi/server/live.py", "python/sadi/core/device.py", "python/tests/server/test_live_audit4.py", "docs/live-view.md"]

[[acceptance]]
text = "hint says Resume live readings; resume returns NoDevice when detached instead of 500; SETTINGS records firmware or literal unknown; tests"
bound = true
+++
