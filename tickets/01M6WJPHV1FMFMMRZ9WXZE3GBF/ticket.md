+++
id = "01M6WJPHV1FMFMMRZ9WXZE3GBF"
title = "Fix test_labs_import_only_core_public_api: lctt/capture.py imports sadi.store.events"
type = "bug"
category = "in-progress"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-08T03:19:43Z"
updated = "2026-11-08T03:23:49Z"
scope = ["python/sadi/labs/lctt/capture.py", "python/sadi/core/**", "python/tests/core/test_lab_registry.py", "docs/core/**"]

[[acceptance]]
text = "Labs import only the core public API (test_labs_import_only_core_public_api passes)"
bound = true
+++

Test fails on main: labs must import only the core public API, but capture.py imports sadi.store.events. Either re-export the needed names via the core public API or inject them. Do not weaken the test.
