+++
id = "01M6WJHVTHVAC5CQ3GFA2YBMPV"
title = "doctor: EXT-020..050, NET-030/040, PY-050/060"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:17:10Z"
updated = "2026-11-08T04:04:38Z"
scope = ["python/sadi/doctor/**", "python/tests/doctor/**", "docs/doctor.md", "docs/doctor-checks.md"]

[[acceptance]]
text = "Doctor checks EXT-020..050, NET-030/040 and PY-050/060 each report every declared failure mode with a remedy for linux, wsl, macos and windows"
bound = true

[[acceptance]]
text = "NET-040 runs only with --running; the doctor stays read-only"
bound = true
+++

found while working ~V3H5CGF: deferred checks
