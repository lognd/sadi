+++
id = "01M7274EKWS410XEGZGFD6HWHK"
title = "M8: calibration layout - capture card above Finish, one vocabulary"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T07:53:02Z"
updated = "2026-11-10T08:01:14Z"
labels = ["creates:web/src/screens/run/pointCount.ts"]
scope = ["web/src/components/wizard/stepGuide.ts", "web/src/screens/run/phases.ts", "web/src/screens/run/RunView.tsx", "web/src/screens/run/inputFields.ts", "web/src/components/wizard/FrontPanel.tsx", "web/src/components/wizard/NextActionPanel.tsx", "web/src/components/wizard/WizardShell.tsx", "web/src/components/wizard/wizard.test.tsx", "web/src/screens/run/RunScreen.tsx", "web/src/screens/run/RunScreen.test.tsx", "web/src/styles.css", "web/src/screens/run/pointCount.ts"]

[[acceptance]]
text = "Capture card (inputs + Accept point (Space) + Mark) directly under Do this and above Finish; Finish secondary and disabled until min points; one verb/noun per action across stepGuide/phases/RunView; phase-specific mark text; vitest passes"
bound = true
+++
