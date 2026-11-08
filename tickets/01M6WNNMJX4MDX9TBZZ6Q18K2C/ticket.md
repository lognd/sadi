+++
id = "01M6WNNMJX4MDX9TBZZ6Q18K2C"
title = "WAL POINT must persist settled, forced-early and drift flags (not only phase/window/inputs)"
type = "task"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-08T04:11:39Z"
updated = "2026-11-08T04:14:40Z"
labels = ["python"]
scope = ["python/sadi/core/point_inputs.py", "python/sadi/api/acquisition.py", "python/sadi/labs/lctt/capture.py", "python/sadi/server/curve_source.py"]
+++

RJDN26D wired capture to record_point, but settled/forced-early/drift/t_since_load_s stay only on the in-memory Captured.point. After crash recovery these are lost. Persist them in the POINT event (extend point_inputs mapping and curve_source/recover_state replay) with a round-trip test. Data-safety: nothing recorded may be lost on recovery.
