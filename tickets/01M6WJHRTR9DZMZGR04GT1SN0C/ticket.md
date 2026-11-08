+++
id = "01M6WJHRTR9DZMZGR04GT1SN0C"
title = "doctor: SESS, WAL layers"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:17:07Z"
updated = "2026-11-08T03:37:51Z"
scope = ["python/sadi/doctor/**", "python/tests/doctor/**", "docs/doctor.md", "docs/doctor-checks.md"]

[[acceptance]]
text = "Every SESS-* and WAL-* catalog check reports each declared mode read-only, with a remediation for all four OSes, and the survey never modifies a session"
bound = false
+++

found while working ~V3H5CGF: spec layers not implemented
