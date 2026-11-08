+++
id = "01M6WK3STJ55FH80KFAPYEFC79"
title = "Audit StrEnum error families (StoreCode etc, JobState, DeviceStatus) -> typani ErrorSet; unify writer_thread errors with StoreCode"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:26:57Z"
updated = "2026-11-08T04:04:41Z"
scope = ["python/sadi/core/errors.py", "python/sadi/store/writer_thread.py", "python/tests/core/test_models.py", "docs/core/models.md"]

[[acceptance]]
text = "Error code families are typani ErrorSet with stable wire values; writer errors carry StoreCode; remaining StrEnums recorded as states"
bound = false
+++
