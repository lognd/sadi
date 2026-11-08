+++
id = "01M6WX1VCKPVMHTTEYDJHD0PCY"
title = "Add figure-data export format to LcttLab"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T06:20:39Z"
updated = "2026-11-08T06:32:18Z"
labels = ["creates:python/sadi/labs/lctt/figure_data.py", "creates:docs/lctt/figure-data.md"]
scope = ["python/sadi/labs/lctt/**", "python/tests/labs/lctt/**", "docs/lctt/**", "docs/server/export.md", "python/sadi/labs/lctt/figure_data.py", "docs/lctt/figure-data.md"]

[[acceptance]]
text = "lctt-figure-json (application/json) is declared by LcttLab and renders calibration and stress-strain series from RunState.events"
bound = false

[[acceptance]]
text = "Export is read-only, in memory, refused with TOO_FEW_POINTS when no events"
bound = false
+++

Follow-up of QNBQVJW: declare an application/json figure-data export format (stress-strain curve) now that RunState.events carries raw events.
