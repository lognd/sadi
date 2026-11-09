+++
id = "01M6Z65G3QEWKSWGGAGYK5K182"
title = "Audit Ad3Guard._on_signal/close for logging reentrancy: a signal during a logging stream write can raise RuntimeError (reentrant BufferedWriter) and skip the device close"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:38:25Z"
updated = "2026-11-09T03:41:01Z"
idempotency_key = "gap-guard-log-reentrancy"
scope = ["docs/bench/ad3.md", "python/sadi/bench/ad3/launch.py", "python/tests/bench/test_ad3_launch_signals.py"]

[[acceptance]]
text = "SIGTERM with a raising log handler still closes the AD3 exactly once and exits 128+signum"
bound = true
+++
