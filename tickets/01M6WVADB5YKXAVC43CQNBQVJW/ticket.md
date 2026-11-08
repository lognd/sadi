+++
id = "01M6WVADB5YKXAVC43CQNBQVJW"
title = "LcttLab.export_formats is empty so /api/export lists nothing"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T05:50:23Z"
updated = "2026-11-08T06:18:53Z"
labels = ["lab"]
scope = ["python/sadi/labs/lctt/**", "python/tests/labs/lctt/**", "python/tests/server/**", "python/sadi/server/**", "python/sadi/core/**", "python/tests/core/**", "docs/lctt/**", "docs/server/**", "docs/core/**"]
+++

Real lctt lab declares no export formats; add CSV (32-column) and figure-data formats. Blocked on private reference header check ~SYDV1C9 for column names.
