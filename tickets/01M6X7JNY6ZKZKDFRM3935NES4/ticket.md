+++
id = "01M6X7JNY6ZKZKDFRM3935NES4"
title = "Export screen figure PNG/SVG button sends no export request in the guided run"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T09:24:36Z"
updated = "2026-11-08T09:50:14Z"
scope = ["web/src/screens/export/**", "web/e2e/guided-run.spec.ts", "docs/e2e.md"]

[[acceptance]]
text = "Given a finished guided run, when the figure PNG button is pressed on the Export screen, then a calibration PNG download fires."
bound = true
+++

found while working ~WV4W4WY: after a full guided run under --sim, pressing 'Export ... as PNG' produces no download and no /api/export request in the server log; guided-run.spec.ts only asserts the button is visible.
