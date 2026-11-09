+++
id = "01M6Z5G0SEZ5PNGG11RYBAN6G3"
title = "Doctor EXT-040: probe SADI via explicit --port / SADI_PORT when sadi_py lacks udev enumeration, with clear remediation"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:26:41Z"
updated = "2026-11-09T03:29:40Z"
idempotency_key = "gap-ext040-port"
scope = ["python/sadi/doctor/checks/ext.py", "python/tests/doctor/test_ext_040_port.py", "docs/doctor.md"]

[[acceptance]]
text = "EXT-040 passes as 'enumeration unsupported' when an explicit port (--port or SADI_PORT) answers without udev, and warns with step-by-step port remediation otherwise"
bound = true
+++
