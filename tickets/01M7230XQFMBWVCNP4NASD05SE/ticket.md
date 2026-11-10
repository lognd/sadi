+++
id = "01M7230XQFMBWVCNP4NASD05SE"
title = "Audit2 H6: excluded calibration/tare/specimen points still used by CSV export and calibration plot"
type = "bug"
category = "in-progress"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-10T06:41:12Z"
updated = "2026-11-10T06:45:45Z"
labels = ["creates:python/tests/server/test_export_exclusions.py"]
scope = ["python/sadi/server/curve_source.py", "python/sadi/server/routes/plots.py", "python/sadi/server/routes/export.py", "python/tests/server/test_export_exclusions.py", "docs/web/review-screen.md"]

[[acceptance]]
text = "session_events honours exclusions for all point kinds; test: excluding a cal point changes CSV slope and plot fit"
bound = false
+++
