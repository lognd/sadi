+++
id = "01M6WP144S0ENPQESCQEQ6NT5Y"
title = "Replay: carry settled/forced-early/drift flags from WAL POINT onto LoadPoint events used by the fit"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T04:17:55Z"
updated = "2026-11-08T04:18:25Z"
labels = ["creates:python/tests/server/test_curve_flags.py"]
scope = ["python/sadi/server/curve_source.py"]
+++

found while working ~6Q18K2C: server/curve_source.py parses PointMeta via parse_meta and logs forced-early points but does not attach the flags to the LoadPoint events, so the fit cannot exclude or mark them. Scope: python/sadi/server/curve_source.py, python/sadi/core/** as needed, python/tests/server/**, docs/server/app.md.
