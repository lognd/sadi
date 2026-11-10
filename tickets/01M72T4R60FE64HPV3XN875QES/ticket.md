+++
id = "01M72T4R60FE64HPV3XN875QES"
title = "Restyle: sentence-case readable long labels; white sans export theme"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T13:25:15Z"
updated = "2026-11-10T13:28:57Z"
labels = ["creates:none"]
scope = ["web/src/styles.css", "web/src/plots/theme.ts", "web/src/screens/run/inputFields.ts", "web/src/plots/core/export.ts", "web/src/plots/core/index.ts", "web/src/plots/core/plots.test.ts", "web/src/screens/run/RunView.tsx", "web/src/screens/run/inputFields.test.ts", "web/src/screens/run/RunScreen.test.tsx", "docs/web/design-system.md"]

[[acceptance]]
text = "Labels over 3 words or instruction-bearing use sentence case at --text-sm; hanger clause moved to helper text; exportScene uses white background and sans font stack; snapshots updated"
bound = true
+++

Audit6 L4,L5.
