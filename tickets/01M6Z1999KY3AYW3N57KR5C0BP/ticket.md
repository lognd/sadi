+++
id = "01M6Z1999KY3AYW3N57KR5C0BP"
title = "doctor USB-070: fix command uses wrong sysfs path; use find on /sys for latency_timer (WSL path is /sys/devices/platform/vhci_hcd.0/...)"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-09T02:13:06Z"
updated = "2026-11-09T02:19:38Z"
idempotency_key = "lat070"
scope = ["docs/doctor-checks.md", "docs/doctor.md", "python/sadi/doctor/checks/usb.py", "python/tests/doctor/test_sadi_doctor.py"]

[[acceptance]]
text = "Given a WSL ttyUSB node whose latency_timer is not 2, when USB-070 runs, then the fix emits the resolved real sysfs path per node"
bound = true
+++
