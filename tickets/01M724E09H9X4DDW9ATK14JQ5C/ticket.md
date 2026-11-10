+++
id = "01M724E09H9X4DDW9ATK14JQ5C"
title = "Wire LiveAcquisition.finish() into results/export and show stop_reason/fault in the UI"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T07:05:50Z"
updated = "2026-11-10T07:21:54Z"
labels = ["creates:python/tests/server/test_finish_wiring.py"]
scope = ["python/sadi/server/service.py", "python/sadi/server/routes/results.py", "python/tests/server/test_finish_wiring.py"]

[[acceptance]]
text = "Reaching Results/Export (or closing the session) calls finish(); the health/status API exposes stop_reason and fault; test asserts no raw blocks after finish"
bound = false
+++
