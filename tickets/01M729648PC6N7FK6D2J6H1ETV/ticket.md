+++
id = "01M729648PC6N7FK6D2J6H1ETV"
title = "audit4 M2: recovered spill becomes a fragment version without calibration/tare; spill not idempotent across Close retries"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T08:28:54Z"
updated = "2026-11-10T08:41:56Z"
labels = ["audit4"]
scope = ["python/sadi/store/spill.py", "python/sadi/server/service.py", "python/sadi/server/routes/sessions.py", "python/tests/store", "python/sadi/store/manifest.py", "docs/data-safety.md", "python/tests/server/test_latest_lineage.py"]

[[acceptance]]
text = "import_spill produces a complete self-contained successor (parent verified records plus spill) and spill files are named deterministically so retries do not duplicate; tests"
bound = true
+++
