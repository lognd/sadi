+++
id = "01M6WJHVXTWDD0RA55508QAN2W"
title = "doctor: USB-010, USB-060..080 and Windows/macOS USB support"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:17:10Z"
updated = "2026-11-08T04:23:59Z"
scope = ["python/sadi/doctor/**", "python/tests/doctor/**", "docs/doctor.md", "docs/doctor-checks.md"]

[[acceptance]]
text = "USB-010, USB-060, USB-070 and USB-080 exist with a remedy per mode for all four OSes"
bound = true

[[acceptance]]
text = "USB-020..050 run (not skip) on Windows and macOS"
bound = true

[[acceptance]]
text = "docs/doctor.md and docs/doctor-checks.md are current"
bound = true
+++

found while working ~V3H5CGF: USB skips unverified off Linux/WSL
