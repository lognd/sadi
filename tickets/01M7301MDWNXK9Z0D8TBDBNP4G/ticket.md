+++
id = "01M7301MDWNXK9Z0D8TBDBNP4G"
title = "Planner GUI/CLI: derive calibration from entered height/voltage points (no typed slope)"
type = "story"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T15:08:24Z"
updated = "2026-11-10T15:19:38Z"
labels = ["creates:python/tests/design/test_cal_fit.py"]
scope = ["python/sadi/design/**", "python/tests/design/**", "docs/design/**"]

[[acceptance]]
text = "GUI and CLI accept calibration points as height(m)/volts pairs (table rows / --cal-points h:v,...) and fit slope, intercept and their uncertainty by least squares; no slope field is required"
bound = true

[[acceptance]]
text = "Fit slope/intercept/se/r2/n are shown to the operator; fewer than 2 distinct heights is a clear error, never a default"
bound = true

[[acceptance]]
text = "Fit uncertainty (slope se) propagates into predicted-volts uncertainty in the plan"
bound = true

[[acceptance]]
text = "Existing --cal-slope remains only as an explicit override, labelled as such"
bound = true
+++

User: the tool must be a weight/height planner; we GET the calibration from the height/voltage data. Reuse the lctt fit (python/sadi/labs/lctt/calibration.py) if the layering allows, else extract shared fit code; no duplication.
