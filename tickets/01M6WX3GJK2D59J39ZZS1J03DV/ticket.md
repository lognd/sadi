+++
id = "01M6WX3GJK2D59J39ZZS1J03DV"
title = "CSV export: add per-quantity uncertainty columns missing from PointRow"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T06:21:34Z"
updated = "2026-11-08T06:37:30Z"
scope = ["python/sadi/labs/lctt/export_csv.py,python/tests/labs/lctt/**,docs/lctt/export-csv.md", "python/sadi/labs/lctt/export_csv.py", "docs/lctt/export-csv.md", "python/tests/labs/lctt/test_export_csv.py", "python/tests/labs/lctt/test_lab_export.py"]

[[acceptance]]
text = "PointRow has the listed uncertainty fields; round-trip test passes"
bound = false
+++

Found while working ~SYDV1C9. The reference carries uncertainty columns for tare, voltage difference, displacement, gauge length, hanger load, diameter and secant modulus that PointRow lacks. Proposal: add the uncertainty fields computed by the engines (propagated), update reader, writer, docs.
