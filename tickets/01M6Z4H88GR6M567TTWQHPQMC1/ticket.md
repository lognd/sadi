+++
id = "01M6Z4H88GR6M567TTWQHPQMC1"
title = "doctor USB-070: step-by-step fix for FTDI latency_timer 16 -> 2 on WSL (udev/sysfs, read-only guidance plus fix --apply command)"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:09:53Z"
updated = "2026-11-09T03:12:57Z"
idempotency_key = "usb070-latency"
scope = ["python/sadi/doctor/checks/usb.py", "python/tests/doctor/test_sadi_doctor.py", "changelog.d/01M6Z4H88GR6M567TTWQHPQMC1.changed.md", "docs/doctor-checks.md"]

[[acceptance]]
text = "USB-070 fix gives set-now, persistent udev rule and verify steps; test passes"
bound = true
+++
