+++
id = "01M6WJ8R4E0K2Z5K5KZJTJA6QM"
title = "Add Setup wizard step (Phase.SETUP) hosting clamp-slip sub-check"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:12:11Z"
updated = "2026-11-08T03:50:18Z"
scope = ["python/sadi/core/models.py,python/sadi/labs/lctt/plugin.py,python/tests/plugins/test_lctt_plugin.py", "python/sadi/core/models.py", "python/sadi/labs/lctt/plugin.py", "python/tests/plugins/test_lctt_plugin.py", "docs/core/models.md", "docs/lctt/clamp-check.md", "changelog.d/01M6WJ8R4E0K2Z5K5KZJTJA6QM.changed.md"]

[[acceptance]]
text = "LcttLab.steps() begins with a Phase.SETUP step hosting the clamp-slip sub-check, gated by min_points = cycles"
bound = true
+++

found while working DQ1C3W6: clamp_check.setup_subcheck() exists but LcttLab.steps() has no Setup step; needs core Phase value.
