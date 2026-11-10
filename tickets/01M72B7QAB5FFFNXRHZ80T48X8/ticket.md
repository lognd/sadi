+++
id = "01M72B7QAB5FFFNXRHZ80T48X8"
title = "Fix capture/pipeline regressions from settle auto-open (found in ~6ZE1QAP)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T09:04:44Z"
updated = "2026-11-10T09:22:13Z"
scope = ["python/sadi/labs/lctt/capture.py", "python/tests/labs/lctt/test_capture.py", "python/tests/core/test_pipeline.py"]

[[acceptance]]
text = "CaptureController restarts its max-wait clock after a capture (auto-opened point); test_tick_after_capture_is_noop and test_pipeline settle test pass"
bound = true
+++
