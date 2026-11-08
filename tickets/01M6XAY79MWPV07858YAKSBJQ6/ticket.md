+++
id = "01M6XAY79MWPV07858YAKSBJQ6"
title = "Reduce remaining COV001 findings in python/sadi (about 40 left)"
type = "task"
category = "in-progress"
priority = "low"
points = 3
reporter = "lognd"
created = "2026-11-08T10:23:20Z"
updated = "2026-11-08T10:34:14Z"
scope = ["python/tests/api/**", "python/tests/cli/**", "python/tests/core/**", "python/tests/doctor/**", "python/tests/jobs/**", "python/tests/labs/lctt/**", "python/tests/plugins/**"]

[[acceptance]]
text = "COV001 count under python/sadi reduced below 10 with real tests or frob:tests markers; no test weakened"
bound = true
+++

Follow-up to ACKX0VE (128 -> 40). Remaining: pool.py send_run/send_cancel/join, live.py and guidance.py symbols, wizard/probes/lock/writer_thread. frob:accept cannot park Unresolved findings; bind with real tests.
