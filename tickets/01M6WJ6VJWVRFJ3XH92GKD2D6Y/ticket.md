+++
id = "01M6WJ6VJWVRFJ3XH92GKD2D6Y"
title = "Validate LCTT loading against docs oracle (oracle moved to private)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T03:11:09Z"
updated = "2026-11-08T06:24:07Z"
scope = ["python/tests/labs/lctt/test_loading.py", "docs/lctt/loading.md"]

[[acceptance]]
text = "Private test checks compute_loading against every row of the local short-run reference at 1e-9 (force, stress, strain, uncertainties; not E)"
bound = false
+++

found while working ~9TZ8D2S: expected_values.py and weight inventory are no longer tracked, so acceptance 3 (1e-9 vs short-run file) is validated only against closed forms
