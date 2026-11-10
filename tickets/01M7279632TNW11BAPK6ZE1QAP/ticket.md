+++
id = "01M7279632TNW11BAPK6ZE1QAP"
title = "M4: auto-open settle point after each captured point; align settle vocabulary"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T07:55:37Z"
updated = "2026-11-10T08:04:26Z"
scope = ["python/sadi/labs/lctt/settle_stream.py", "python/tests/labs/lctt/test_capture.py", "python/tests/labs/lctt/test_settle_stream.py"]

[[acceptance]]
text = "settle verdict does not latch; a settle point opens automatically after each POINT in calibration/tare; tests"
bound = true
+++
