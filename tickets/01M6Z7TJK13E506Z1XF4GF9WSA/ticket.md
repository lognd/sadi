+++
id = "01M6Z7TJK13E506Z1XF4GF9WSA"
title = "Flaky: test_sigterm_subprocess_single_close_exit_code fails in full pytest run, passes alone"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T04:07:24Z"
updated = "2026-11-09T04:13:05Z"
idempotency_key = "gap-sigterm-flaky-fullsuite"

[[acceptance]]
text = "tests/bench/test_ad3_launch_signals.py passes repeatedly under CPU load (root cause: print(READY) race fixed in a64c64f5)"
bound = true
+++
