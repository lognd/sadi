+++
id = "01M6WJHW0YH103PNS1PGAG48CQ"
title = "doctor: fix subcommand, --bundle, unified sadi launcher registration"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:17:10Z"
updated = "2026-11-08T03:59:01Z"
scope = ["python/sadi/doctor/**", "python/tests/doctor/**", "docs/doctor.md"]

[[acceptance]]
text = "sadi doctor fix CHECK-ID is a dry run by default and runs only confirmed fixable system/process commands, never data, data-dir or data-root ones"
bound = true

[[acceptance]]
text = "sadi doctor --bundle PATH writes a redacted zip to a new path with no-replace semantics and refuses existing or data-root paths"
bound = true
+++

found while working ~V3H5CGF: CLI gaps
