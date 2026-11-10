+++
id = "01M7242CRQGBYWTR080XEYNFS9"
title = "Audit2 H8a: start real mode without a board (status disconnected) instead of exit 6"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T06:59:29Z"
updated = "2026-11-10T07:03:09Z"
labels = ["creates:python/tests/test_launcher_no_device.py"]
scope = ["python/sadi/launcher.py", "python/tests/test_launcher_no_device.py", "python/tests/cli/test_launcher_real_device.py", "docs/server/launcher.md"]

[[acceptance]]
text = "sadi serve with an unopenable board port starts, serves the UI and read endpoints, reports device disconnected, blocks capture with the existing hint, and exits 0 on shutdown"
bound = true
+++
