+++
id = "01M727VHZTQHYABYCT6XTASEM1"
title = "L4: two contradictory save indicators; Saved shown with no session"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T08:05:39Z"
updated = "2026-11-10T08:06:52Z"
scope = ["web/src/components/status/StatusBar.tsx", "web/src/components/wizard/WizardShell.tsx", "web/src/App.tsx", "web/src/screens/run/RunScreen.tsx", "web/src/components/wizard/wizard.test.tsx", "web/src/components/instrument/audit1.test.tsx", "web/src/components/status/saveView.ts", "web/src/components/status/saveView.test.ts"]

[[acceptance]]
text = "One save indicator source; never shows Saved without an open session; test covers both"
bound = false
+++
