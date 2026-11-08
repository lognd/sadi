+++
id = "01M6WMGMJE0WEXXNQ3AD754A8M"
title = "Wire stress-strain onWindowChange to API refit"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:51:27Z"
updated = "2026-11-08T03:55:06Z"
labels = ["feature", "creates:web/src/api/refit.ts"]
scope = ["web/src/api/refit.ts"]
+++

StressStrainPlot onWindowChange is callback-only. Host screen must call the API refit and re-render; add an endpoint client and a test.
