+++
id = "01M6WNNMJX4MDX9TBZZ6Q18K2C"
title = "WAL POINT must persist settled, forced-early and drift flags (not only phase/window/inputs)"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-08T04:11:39Z"
updated = "2026-11-08T04:16:01Z"
labels = ["python"]
scope = ["python/sadi/core/point_inputs.py", "python/sadi/api/acquisition.py", "python/sadi/labs/lctt/capture.py", "python/sadi/server/curve_source.py", "docs/server/app.md", "docs/api/acquisition.md", "docs/lctt/capture.md", "creates:python/tests/core/test_point_meta.py", "python/tests/core/test_point_meta.py", "changelog.d/01M6WNNMJX4MDX9TBZZ6Q18K2C.changed.md"]

[[acceptance]]
text = "POINT events persist settled, forced_early, drift_rate and t_since_load_s and recover_state returns them unchanged"
bound = true

[[acceptance]]
text = "POINT events without the meta fields still parse (defaults)"
bound = true
+++

RJDN26D wired capture to record_point, but settled/forced-early/drift/t_since_load_s stay only on the in-memory Captured.point. After crash recovery these are lost. Persist them in the POINT event (extend point_inputs mapping and curve_source/recover_state replay) with a round-trip test. Data-safety: nothing recorded may be lost on recovery.
