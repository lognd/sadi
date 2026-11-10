+++
id = "01M72TEVXXFP3PZ84SABZEDX7H"
title = "Run screen: drive guidance next-weight line from design selector (single source)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T13:30:47Z"
updated = "2026-11-10T13:35:14Z"
labels = ["creates:none"]
scope = ["web/src/screens/run/RunScreen.tsx", "web/src/screens/run/RunScreen.test.tsx", "web/src/screens/run/guidance.ts"]

[[acceptance]]
text = "Guidance nextAction derives from /api/design/next-weight or drops the load; test that values shown on one screen cannot differ"
bound = true
+++

Audit6 M5 follow-up from ~78KV8YS. RunScreen guidance-note (GpLoadSuggester/EvenScheduleSuggester) can disagree with SuggestedWeightPanel. Make one source.
