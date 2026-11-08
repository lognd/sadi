+++
id = "01M6WJT055W0QPZYNF862E6T8C"
title = "Wire AcquisitionPipeline to device and API layers (load chain, tick timer)"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:21:36Z"
updated = "2026-11-08T03:56:53Z"
scope = ["python/sadi/api/**", "python/tests/api/**", "docs/api/**", "docs/core/pipeline.md"]

[[acceptance]]
text = "Every block from the source and its stop tail is ingested into the WAL"
bound = true

[[acceptance]]
text = "Load chain writes ordered load markers and never skips on refusal"
bound = true

[[acceptance]]
text = "Device fault halts acquisition loudly while saved blocks stay saved"
bound = true
+++

found while working ~60ZNFTD
