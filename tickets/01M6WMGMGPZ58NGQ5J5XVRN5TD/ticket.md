+++
id = "01M6WMGMGPZ58NGQ5J5XVRN5TD"
title = "Fix lctt export_csv import-boundary test failures"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-08T03:51:26Z"
updated = "2026-11-08T03:53:33Z"
labels = ["bug"]
scope = ["python/sadi/labs/lctt/export_csv.py", "python/sadi/core/export_api.py", "docs/core/lab-modules.md"]

[[acceptance]]
text = "lctt export_csv imports only the core public API (sadi.core.export_api); boundary tests pass without loosening"
bound = true

[[acceptance]]
text = "Export publish semantics (atomic, no-replace) unchanged"
bound = true
+++

tests/plugins/test_boundary.py::test_plugin_imports_within_boundary (lctt) and tests/core/test_lab_registry.py::test_labs_import_only_core_public_api fail: python/sadi/labs/lctt/export_csv.py imports sadi.store.csv_export and sadi.store.exports. Route through the core public API or an allowed seam.
