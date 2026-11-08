+++
id = "01M6WKE8GD0PZNEM6E87VE6XWX"
title = "Covariance registry grows without bound; register_derived is O(registry)"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:32:40Z"
updated = "2026-11-08T03:36:24Z"
scope = ["python/sadi/uncertainty/covariance.py", "python/sadi/uncertainty/measured.py", "docs/uncertainty/measured.md", "python/tests/uncertainty/test_registry_scaling.py", "python/tests/labs/lctt/test_live.py"]

[[acceptance]]
text = "Registry size stays bounded after dropping Measured values and register_derived cost is independent of unrelated registry entries"
bound = true
+++

found while working 01M6W7R3J00J2HQ7XPW19WDD6Q: DEFAULT_REGISTRY never forgets Measured ids and register_derived loops over every id, so a live session per-point update slows to ~35-55 ms by point 200 (threatens the <50 ms live budget). Fix: per-session registry or weak/ref-counted entries.
