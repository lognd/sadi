+++
id = "01M6Z5J0CK9PM3NFHKN84QQJAV"
title = "Verify Ad3Guard SIGTERM/SIGHUP handlers coexist with uvicorn shutdown (restore prior handlers, close exactly once, test with subprocess)"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:27:46Z"
updated = "2026-11-09T03:31:11Z"
idempotency_key = "gap-ad3guard-signals"
scope = ["python/sadi/bench/ad3/launch.py", "python/tests/bench/test_ad3_launch_signals.py"]

[[acceptance]]
text = "Ad3Guard closes the device exactly once on SIGTERM/SIGHUP (alone and under uvicorn), restores prior handlers, installs only on the main thread"
bound = false
+++
