+++
id = "01M6WMGMJE0WEXXNQ3AD754A8M"
title = "Wire stress-strain onWindowChange to API refit"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:51:27Z"
updated = "2026-11-08T03:56:27Z"
labels = ["feature", "creates:web/src/api/refit.ts", "creates:web/src/api/refit.test.ts", "creates:web/src/screens/StressStrainScreen.tsx", "creates:web/src/screens/StressStrainScreen.test.tsx"]
scope = ["web/src/api/refit.ts", "web/src/api/refit.test.ts", "web/src/screens/StressStrainScreen.tsx", "web/src/screens/StressStrainScreen.test.tsx", "docs/web/stress-strain-plot.md"]

[[acceptance]]
text = "Changing the fit window calls the refit client and re-renders E, r^2 and uncertainty"
bound = true

[[acceptance]]
text = "A failed refit shows an error and keeps the previous fit and all data"
bound = false
+++

StressStrainPlot onWindowChange is callback-only. Host screen must call the API refit and re-render; add an endpoint client and a test.
