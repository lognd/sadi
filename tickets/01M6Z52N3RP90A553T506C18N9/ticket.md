+++
id = "01M6Z52N3RP90A553T506C18N9"
title = "Doctor: persist SADI_DWF_LIB story (detect libdwf, give step-by-step export/launcher config)"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:19:23Z"
updated = "2026-11-09T03:25:26Z"
idempotency_key = "gap-dwf-lib-persist"
scope = ["python/sadi/doctor/checks/ad3.py", "python/tests/doctor/test_ad3_checks.py"]

[[acceptance]]
text = "Doctor AD3-020/AD3-050 remedies give ordered locate, persist and verify steps for SADI_DWF_LIB"
bound = true
+++
