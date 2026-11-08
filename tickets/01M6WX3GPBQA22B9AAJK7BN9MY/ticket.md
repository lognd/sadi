+++
id = "01M6WX3GPBQA22B9AAJK7BN9MY"
title = "CSV export: store raw calibration points in metadata for full re-analysis"
type = "task"
category = "todo"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T06:21:34Z"
updated = "2026-11-08T06:39:05Z"
scope = ["python/sadi/labs/lctt/export_csv.py,python/tests/labs/lctt/**,docs/lctt/export-csv.md"]

[[acceptance]]
text = "Reader rebuilds CalPoint events from the file; round-trip test passes"
bound = false
+++

Found while working ~SYDV1C9. The reference metadata stores each raw calibration point and per-input reading statistics; ours stores only the fit so to_live_events cannot rebuild CalPoint. Proposal: add numbered calibration point rows to the metadata block and read them back.
