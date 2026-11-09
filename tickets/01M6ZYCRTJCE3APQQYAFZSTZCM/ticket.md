+++
id = "01M6ZYCRTJCE3APQQYAFZSTZCM"
title = "doctor fix --apply: allow DATA-010 mkdir and WEB-010 build"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T10:41:49Z"
updated = "2026-11-09T10:45:07Z"
idempotency_key = "doctor-apply-mkdir-build"
scope = ["python/sadi/doctor/**", "python/tests/doctor/**", "docs/doctor.md"]

[[acceptance]]
text = "fix --apply plans the DATA-010 mkdir and WEB-010 build after y/N; data steps never run"
bound = true
+++
