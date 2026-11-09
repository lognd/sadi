+++
id = "01M6Z52N7A69ET20H5GMS8S7BG"
title = "Launcher integration for the AD3 wrapper (open_ad3 via sadi launcher, closes device on exit)"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:19:23Z"
updated = "2026-11-09T03:26:36Z"
idempotency_key = "gap-launcher-ad3"
scope = ["python/sadi/launcher.py", "python/sadi/bench/ad3/**", "python/tests/bench/test_ad3_launch.py", "python/tests/cli/test_launcher_ad3.py", "docs/bench/ad3.md", "docs/server/launcher.md"]

[[acceptance]]
text = "sadi serve --ad3 opens the AD3 via open_managed_ad3 and always closes it on exit; missing libdwf/device is a clean Err"
bound = true
+++
