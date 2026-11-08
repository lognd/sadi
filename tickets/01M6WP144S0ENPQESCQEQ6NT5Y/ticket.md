+++
id = "01M6WP144S0ENPQESCQEQ6NT5Y"
title = "Replay: carry settled/forced-early/drift flags from WAL POINT onto LoadPoint events used by the fit"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T04:17:55Z"
updated = "2026-11-08T04:19:41Z"
labels = ["creates:python/tests/server/test_curve_flags.py"]
scope = ["python/sadi/server/curve_source.py", "python/sadi/labs/lctt/live.py", "python/tests/server/test_curve_flags.py", "docs/server/app.md"]

[[acceptance]]
text = "Replayed LoadPoint events carry settled, forced_early, drift_rate and t_since_load_s from the WAL POINT"
bound = true

[[acceptance]]
text = "Older POINTs without meta replay with default flags"
bound = true
+++

found while working ~6Q18K2C: server/curve_source.py parses PointMeta via parse_meta and logs forced-early points but does not attach the flags to the LoadPoint events, so the fit cannot exclude or mark them. Scope: python/sadi/server/curve_source.py, python/sadi/core/** as needed, python/tests/server/**, docs/server/app.md.
