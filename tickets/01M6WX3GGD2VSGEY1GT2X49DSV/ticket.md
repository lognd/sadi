+++
id = "01M6WX3GGD2VSGEY1GT2X49DSV"
title = "CSV export: add elapsed-time and per-sample std dev columns"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T06:21:34Z"
updated = "2026-11-08T06:33:36Z"
scope = ["python/sadi/labs/lctt/export_csv.py,python/tests/labs/lctt/**,docs/lctt/export-csv.md", "python/sadi/labs/lctt/export_csv.py", "python/tests/labs/lctt/**", "docs/lctt/export-csv.md"]

[[acceptance]]
text = "PointRow carries elapsed time and sample std dev; round-trip test passes"
bound = false
+++

Found while working ~SYDV1C9. The lab reference export has an elapsed-time column and a per-sample voltage standard deviation column that PointRow lacks. Proposal: add both fields (and capture them from live samples), update reader, writer, docs.
