+++
id = "01M729642YCP4MRYBWBNQBYW7A"
title = "audit4 H1+M3: CSV/plot/figure/refit use one gauge length for both specimens; tare uncertainty differs from Results"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T08:28:54Z"
updated = "2026-11-10T08:31:10Z"
labels = ["audit4"]
scope = ["python/sadi/labs/lctt/export_csv.py", "python/sadi/labs/lctt/figure_data.py", "python/sadi/server/curve_source.py", "python/sadi/labs/lctt/lab.py", "python/tests/labs/lctt", "python/sadi/labs/lctt/live.py", "docs/lctt/export-csv.md"]

[[acceptance]]
text = "build_document splits elastic (L0 0.5) and plastic (L0 0.08313) runs, fits E on elastic only and yield on plastic only, adds phase column, CSV E/Yield/Tare u equal /api/results; a test asserts equality"
bound = false
+++
