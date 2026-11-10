+++
id = "01M72PGN2KAMZP8EPHDPV143B4"
title = "Gaussian-process height (weight) selector: advisory next-load suggestion and stop indicator"
type = "story"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T12:21:51Z"
updated = "2026-11-10T12:26:12Z"
labels = ["python", "web"]
scope = ["python/sadi/design/*", "python/sadi/server/routes/design.py", "python/tests/design/*", "docs/design/*", "web/src/screens/run/*", "python/sadi/server/app.py", "web/src/api/schema.ts", "web/src/components/guidance/GpLoadPanel.test.tsx"]

[[acceptance]]
text = "GP/sequential-design selector (linear phases + Matern52 GP yield phase), NextSuggestion and ConfidenceIndicator pydantic payloads, deterministic, under 200 ms, advisory only; REST route; Run screen shows suggested next weight and enough-data indicator; simulator benchmark vs random and binary search"
bound = false
+++
