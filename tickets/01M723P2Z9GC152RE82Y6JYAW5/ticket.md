+++
id = "01M723P2Z9GC152RE82Y6JYAW5"
title = "Audit2 H7: write SETTINGS WAL record at session open so Doctor WAL-040 passes"
type = "bug"
category = "in-progress"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-10T06:52:46Z"
updated = "2026-11-10T06:55:43Z"
labels = ["creates:python/tests/server/test_settings_record.py"]
scope = ["python/sadi/server/live.py", "python/sadi/core/pipeline.py", "python/tests/server/test_settings_record.py", "docs/data-safety.md"]

[[acceptance]]
text = "Every new session WAL contains a SETTINGS record; doctor WAL-040 passes on a fresh session; old sessions without it still open"
bound = true
+++

See audit2.md HIGH 7. Data-safety: additive WAL record only, never rewrite existing WAL.
