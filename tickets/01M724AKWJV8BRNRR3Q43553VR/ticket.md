+++
id = "01M724AKWJV8BRNRR3Q43553VR"
title = "Audit2 H8c: working Reconnect and a disconnected status when no board at start"
type = "bug"
category = "todo"
priority = "medium"
reporter = "lognd"
created = "2026-11-10T07:03:59Z"
updated = "2026-11-10T07:03:59Z"
labels = ["creates:python/tests/server/test_reconnect_no_device.py"]
scope = ["python/sadi/core/device.py", "python/sadi/server/live.py", "python/sadi/server/service.py", "python/tests/server/test_reconnect_no_device.py"]

[[acceptance]]
text = "Starting with no board, plugging it in and pressing Reconnect attaches it without restart; status reports disconnected before that; opening a session with no device raises no RuntimeError"
bound = false
+++
