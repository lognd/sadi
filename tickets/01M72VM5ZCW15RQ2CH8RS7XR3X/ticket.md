+++
id = "01M72VM5ZCW15RQ2CH8RS7XR3X"
title = "Spill import marker must be per data root; join failure cleanup; distinct fragment-failed log"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T13:51:09Z"
updated = "2026-11-10T13:51:25Z"
scope = ["python/sadi/store/spill.py", "python/sadi/server/app.py", "python/tests/conftest.py", "python/tests/store/**"]

[[acceptance]]
text = "_already_imported valid only if version_dir exists under current data_root; spill dir isolation autouse in tests; pre-bytes join error removes or labels in-progress sidecar; fragment-failed skip logged WARNING with crashed paths; nothing deleted"
bound = false
+++

Audit7 M5, L5, L6.
