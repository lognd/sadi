+++
id = "01M6XAASFHD7MKMQ79XRD34EXF"
title = "Run: explain that hotkeys are ignored in text fields (U-04)"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T10:12:44Z"
updated = "2026-11-08T10:15:27Z"
scope = ["web/src/keys/keymap.ts", "web/src/keys/useKeyCapture.ts", "web/src/keys/keymap.test.ts", "web/src/screens/run/RunView.tsx", "web/src/screens/run/RunScreen.test.tsx", "web/src/screens/run/RunScreen.usability.md", "docs/usability-report.md", "docs/web/run-screens.md"]

[[acceptance]]
text = "Run screen shows an accessible hint that hotkeys pause in text fields and Esc/Tab returns to them; Esc blurs the field; typing never captures"
bound = true
+++
