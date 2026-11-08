+++
id = "01M6WMVRTG5YQDSZYQQG368G2E"
title = "Add public halt() to AcquisitionPipeline"
type = "task"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T03:57:31Z"
updated = "2026-11-08T04:00:23Z"
labels = ["refactor"]
scope = ["python/sadi/core/pipeline.py", "python/sadi/api/acquisition.py", "python/tests/core/test_pipeline.py", "docs/core/pipeline.md", "docs/api/acquisition.md"]

[[acceptance]]
text = "AcquisitionPipeline.halt() is public, idempotent, and used by AcquisitionDriver without noqa"
bound = true
+++

AcquisitionDriver (python/sadi/api/acquisition.py) calls private pipeline._halt with a noqa. Add a public halt method on AcquisitionPipeline in python/sadi/core and use it.
