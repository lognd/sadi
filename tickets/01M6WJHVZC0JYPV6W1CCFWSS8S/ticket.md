+++
id = "01M6WJHVZC0JYPV6W1CCFWSS8S"
title = "doctor: BRW-020/030, PLAT-020/040, WEB-020, Windows/macOS fstype probe"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:17:10Z"
updated = "2026-11-08T04:29:09Z"
scope = ["python/sadi/doctor/**", "python/tests/doctor/**", "docs/doctor.md", "docs/doctor-checks.md"]

[[acceptance]]
text = "PLAT-020 fails on an architecture mismatch or unsupported CPU and skips UNVERIFIED without a build target"
bound = true

[[acceptance]]
text = "PLAT-040 warns on Windows for long-paths-off, reserved names and trailing dot or space"
bound = false

[[acceptance]]
text = "WEB-020 warns when the UI bundle version differs from the installed SADI"
bound = true

[[acceptance]]
text = "BRW-020 warns on an old or unidentifiable browser"
bound = false

[[acceptance]]
text = "BRW-030 is opt-in via --open-browser and warns when the browser never fetches the throwaway page"
bound = false

[[acceptance]]
text = "DATA-020 probes the filesystem type on Windows and macOS"
bound = true
+++

found while working ~V3H5CGF: deferred checks
