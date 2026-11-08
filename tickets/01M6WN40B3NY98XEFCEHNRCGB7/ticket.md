+++
id = "01M6WN40B3NY98XEFCEHNRCGB7"
title = "Recording side must write WAL POINT events in the phase mapping the fit curve source reads"
type = "task"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-08T04:02:01Z"
updated = "2026-11-08T04:05:29Z"
labels = ["server"]
scope = ["creates:python/sadi/core/point_inputs.py", "python/sadi/core/pipeline.py", "python/sadi/api/acquisition.py", "python/sadi/server/curve_source.py", "creates:python/tests/api/test_point_roundtrip.py"]
+++

From ~F3C3VYD: python/sadi/server/curve_source.py maps WAL POINT phase (calibration, tare, specimen, load) to analysis inputs; mapping documented in docs/server/app.md. Nothing yet records points that way. Make the acquisition/recording path write them, add a round-trip test (record -> recover_state -> fit), and share one mapping definition (no duplication).
