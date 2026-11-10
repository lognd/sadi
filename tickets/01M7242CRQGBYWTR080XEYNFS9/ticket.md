+++
id = "01M7242CRQGBYWTR080XEYNFS9"
title = "Audit2 H8a: start real mode without a board (status disconnected) instead of exit 6"
type = "bug"
category = "todo"
priority = "high"
reporter = "lognd"
created = "2026-11-10T06:59:29Z"
updated = "2026-11-10T06:59:29Z"
labels = ["creates:python/tests/test_launcher_no_device.py"]
scope = ["python/sadi/launcher.py", "python/tests/test_launcher_no_device.py"]

[[acceptance]]
text = "sadi serve with an unopenable board port starts, serves the UI and read endpoints, reports device disconnected, blocks capture with the existing hint, and exits 0 on shutdown"
bound = false
+++
