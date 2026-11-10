+++
id = "01M72VM5TYFDN445BY0W9G68B1"
title = "Design advice: yield uses plastic points only; monotonic non-zero elastic cold start; fix field label text"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T13:51:09Z"
updated = "2026-11-10T13:55:25Z"
scope = ["python/sadi/design/**", "python/sadi/server/routes/design.py", "python/tests/design/**", "python/tests/server/test_design_route.py", "web/src/components/wizard/stepGuide.ts", "web/src/screens/run/phases.ts", "web/src/components/wizard/stepGuide.test.ts", "docs/design/gp-selector.md"]

[[acceptance]]
text = "YIELD pools only plastic points and locates yield near 4.13 kg in the a7 scenario; elastic/yield suggestions never below current hang and never 0 kg once a point exists; Do-this text agrees with the panel; stepGuide/phases name 'Added mass'"
bound = true
+++

Audit7 M1, M2, L2. See audit7.md and a7/yield_pool.py, a7/cold.py.
