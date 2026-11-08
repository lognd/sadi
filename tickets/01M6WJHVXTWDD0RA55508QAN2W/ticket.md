+++
id = "01M6WJHVXTWDD0RA55508QAN2W"
title = "doctor: USB-010, USB-060..080 and Windows/macOS USB support"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:17:10Z"
updated = "2026-11-08T04:23:04Z"
scope = ["python/sadi/doctor/**", "python/tests/doctor/**"]

[[acceptance]]
text = "USB-010, USB-060, USB-070 and USB-080 exist with a remedy per mode for all four OSes"
bound = false

[[acceptance]]
text = "USB-020..050 run (not skip) on Windows and macOS"
bound = false

[[acceptance]]
text = "docs/doctor.md and docs/doctor-checks.md are current"
bound = false
+++

found while working ~V3H5CGF: USB skips unverified off Linux/WSL
