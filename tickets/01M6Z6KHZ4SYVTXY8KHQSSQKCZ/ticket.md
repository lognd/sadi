+++
id = "01M6Z6KHZ4SYVTXY8KHQSSQKCZ"
title = "Fix tests/core/test_phases.py::test_kind_mapping[codec]: phases.to_device_error maps codec to BAD_DATA but test expects PROTOCOL; reconcile with devfacade mapping"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-09T03:46:05Z"
updated = "2026-11-09T03:47:42Z"
idempotency_key = "gap-phases-codec-mapping"
scope = ["docs/core/device.md", "python/tests/core/test_phases.py"]

[[acceptance]]
text = "test_kind_mapping[codec] expects BAD_DATA, matching devfacade and docs"
bound = true
+++
