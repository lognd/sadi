+++
id = "01M724AKWJV8BRNRR3Q43553VR"
title = "Audit2 H8c: working Reconnect and a disconnected status when no board at start"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T07:03:59Z"
updated = "2026-11-10T07:16:14Z"
labels = ["creates:python/tests/server/test_reconnect_no_device.py"]
scope = ["python/sadi/core/device.py", "python/sadi/server/live.py", "python/sadi/server/service.py", "python/tests/server/test_reconnect_no_device.py", "python/sadi/launcher.py", "python/sadi/server/app.py", "python/sadi/server/routes/results.py", "python/tests/test_launcher_no_device.py", "docs/server/launcher.md", "docs/server/app.md", "docs/server/results.md", "changelog.d/*43553VR*", "python/tests/core/test_device.py", "python/sadi/server/device_open.py", "web/src/api/openapi.json", "web/src/api/schema.ts", "python/tests/cli/test_launcher_real_device.py", "changelog.d/01M724AKWJV8BRNRR3Q43553VR.fixed.md"]

[[acceptance]]
text = "Starting with no board, plugging it in and pressing Reconnect attaches it without restart; status reports disconnected before that; opening a session with no device raises no RuntimeError"
bound = true
+++
