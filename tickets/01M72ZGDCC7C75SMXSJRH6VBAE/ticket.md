+++
id = "01M72ZGDCC7C75SMXSJRH6VBAE"
title = "Standalone weight-planner GUI (no sadi session; for use beside LabVIEW) plus cli.py tests/docs"
type = "story"
category = "done"
outcome = "done"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T14:59:00Z"
updated = "2026-11-10T15:03:30Z"
labels = ["ux"]
scope = ["python/sadi/design/**", "python/tests/design/**", "docs/design/**"]

[[acceptance]]
text = "python -m sadi.design.gui starts a 127.0.0.1-only stdlib http server and opens a single self-contained HTML page (no node/tkinter)"
bound = true

[[acceptance]]
text = "Form takes weights (duplicates allowed), u_mass, diameter, L0, cal slope/offset, saturation, captured points; shows ordered hang table with predicted V and uncertainty"
bound = true

[[acceptance]]
text = "Calibration slope is required and never silently defaulted; page says advisory; nothing is written to disk"
bound = true

[[acceptance]]
text = "cli.py has tests and docs; changelog fragment"
bound = true
+++

User wants GUI for weight planning/picking when using the regular LabVIEW VI. tkinter is not installed; use stdlib http.server + inline HTML/JS calling sadi.design.plan.plan. Reuse parsing from cli.py (untracked, adopt it).
