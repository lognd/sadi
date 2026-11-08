+++
id = "01M6WA539PQQY1X1CXX6662Y63"
title = "Hardware checklist rows: udev, by-id naming, FTDI channel A/B, ftdi_sio on WSL, add 0403:6001 to udev rules"
type = "task"
category = "done"
outcome = "done"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-08T00:50:23Z"
updated = "2026-11-08T01:24:00Z"
scope = ["docs/hardware-verification.md", "packaging/udev/99-sadi.rules", "changelog.d/01M6WA539PQQY1X1CXX6662Y63.changed.md"]

[[acceptance]]
text = "hardware-verification.md has checklist rows for udev rules, by-id naming, FTDI channel A/B selection and ftdi_sio on WSL, all marked pending/unverified"
bound = true

[[acceptance]]
text = "99-sadi.rules includes 0403:6001 (tty and usb), labelled unverified"
bound = true

[[acceptance]]
text = "99-sadi.rules header cross-references the new checklist rows (portability.md update split out: its lease is held by another ticket)"
bound = true
+++
