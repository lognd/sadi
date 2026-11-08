+++
id = "01M6WYB1R6FYQ95T8SDQ62G869"
title = "LCTT CSV export format title says 32 columns (schema is 42)"
type = "bug"
category = "in-progress"
priority = "low"
points = 1
reporter = "lognd"
created = "2026-11-08T06:43:09Z"
updated = "2026-11-08T06:46:05Z"
scope = ["python/sadi/labs/lctt/lab.py"]

[[acceptance]]
text = "The lctt-csv export format title reads LCTT CSV with no column count, and the lctt lab tests pass"
bound = true
+++

found while working ~Y079XVA: CSV_FORMAT title in python/sadi/labs/lctt/lab.py reads "LCTT CSV (32 columns)" but the schema is 42 columns
