+++
id = "01M6Z53SMZTVJW9YGWRT1ZA5MF"
title = "AdcModel default full scale 1.25 V does not match real board (+-5.12 V, ~6400 counts/V); reconcile sim vs hardware"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:20:00Z"
updated = "2026-11-09T03:24:02Z"
idempotency_key = "gap-adcmodel-fullscale"
scope = ["python/sadi/bench/*.py", "python/tests/bench/test_lctt_source.py", "docs/bench/lctt-ad3-matrix.md"]

[[acceptance]]
text = "AdcModel default full scale equals the real board's +-5.12 V"
bound = true
+++
