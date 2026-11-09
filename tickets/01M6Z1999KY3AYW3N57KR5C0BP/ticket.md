+++
id = "01M6Z1999KY3AYW3N57KR5C0BP"
title = "doctor USB-070: fix command uses wrong sysfs path; use find on /sys for latency_timer (WSL path is /sys/devices/platform/vhci_hcd.0/...)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-09T02:13:06Z"
updated = "2026-11-09T02:19:00Z"
idempotency_key = "lat070"
scope = ["docs/doctor-checks.md", "docs/doctor.md", "python/sadi/doctor/checks/usb.py", "python/tests/doctor/test_sadi_doctor.py"]
+++
