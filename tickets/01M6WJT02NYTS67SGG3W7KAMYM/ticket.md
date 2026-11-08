+++
id = "01M6WJT02NYTS67SGG3W7KAMYM"
title = "Pipeline: write RAW_JUNK records for dropped_bytes"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:21:36Z"
updated = "2026-11-08T03:28:21Z"
scope = ["python/sadi/core/pipeline.py", "python/tests/core/test_pipeline.py", "docs/core/pipeline.md"]

[[acceptance]]
text = "Blocks with dropped bytes are durably written as RAW_JUNK via the WAL writer"
bound = true
+++

found while working ~60ZNFTD
