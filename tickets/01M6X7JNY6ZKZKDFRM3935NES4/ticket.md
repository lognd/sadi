+++
id = "01M6X7JNY6ZKZKDFRM3935NES4"
title = "Export screen figure PNG/SVG button sends no export request in the guided run"
type = "bug"
category = "todo"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T09:24:36Z"
updated = "2026-11-08T09:35:57Z"
scope = ["web/src/screens/export/**"]
+++

found while working ~WV4W4WY: after a full guided run under --sim, pressing 'Export ... as PNG' produces no download and no /api/export request in the server log; guided-run.spec.ts only asserts the button is visible.
