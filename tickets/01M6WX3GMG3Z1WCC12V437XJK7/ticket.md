+++
id = "01M6WX3GMG3Z1WCC12V437XJK7"
title = "CSV export: decide row-level session constants and force-unit loads vs reference"
type = "task"
category = "todo"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T06:21:34Z"
updated = "2026-11-08T07:12:12Z"
scope = ["python/sadi/labs/lctt/export_csv.py,python/tests/labs/lctt/**,docs/lctt/export-csv.md"]

[[acceptance]]
text = "Decision recorded in docs/lctt/export-csv.md"
bound = false
+++

Found while working ~SYDV1C9. The reference repeats calibration, tare, gauge length, diameter on every row and expresses load and hanger as force; PointRow keeps most in metadata and uses mass. Proposal: decision ticket; if compatibility with the reference is wanted add repeated constants and force columns, else document the intentional divergence.
