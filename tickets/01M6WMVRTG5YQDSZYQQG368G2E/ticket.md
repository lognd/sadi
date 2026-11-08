+++
id = "01M6WMVRTG5YQDSZYQQG368G2E"
title = "Add public halt() to AcquisitionPipeline"
type = "task"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T03:57:31Z"
updated = "2026-11-08T03:59:35Z"
labels = ["refactor"]
+++

AcquisitionDriver (python/sadi/api/acquisition.py) calls private pipeline._halt with a noqa. Add a public halt method on AcquisitionPipeline in python/sadi/core and use it.
