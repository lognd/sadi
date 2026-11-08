+++
id = "01M6WJ8R4E0K2Z5K5KZJTJA6QM"
title = "Add Setup wizard step (Phase.SETUP) hosting clamp-slip sub-check"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:12:11Z"
updated = "2026-11-08T03:49:17Z"
scope = ["python/sadi/core/models.py,python/sadi/labs/lctt/plugin.py,python/tests/plugins/test_lctt_plugin.py", "python/sadi/core/models.py"]
+++

found while working DQ1C3W6: clamp_check.setup_subcheck() exists but LcttLab.steps() has no Setup step; needs core Phase value.
