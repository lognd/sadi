+++
id = "01M7230XMB52H0AA8ETNQ8RBPX"
title = "Audit2 H3/H4: calibration quality gate (r2, slope sign, outliers); plausible ranges for height, mass, diameter; require diameter"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T06:41:12Z"
updated = "2026-11-10T06:43:06Z"
scope = ["python/sadi/core/point_inputs.py", "python/sadi/labs/lctt/lab.py", "web/src/screens/run/RunScreen.test.tsx", "web/src/screens/run/RunScreen.tsx", "web/src/screens/run/RunScreen.usability.md", "web/src/screens/run/RunView.tsx", "web/src/screens/run/capture.ts", "web/src/screens/run/exportTrace.ts", "web/src/screens/run/inputFields.test.ts", "web/src/screens/run/inputFields.ts", "web/src/screens/run/live.ts", "web/src/screens/run/loadChange.ts", "web/src/screens/run/phases.ts", "web/src/screens/run/useRunLive.ts", "python/tests/labs/lctt", "docs/labs/lctt-gp-selector.md", "python/tests/core/test_point_inputs_ranges.py", "python/tests/labs/lctt/**"]

[[acceptance]]
text = "1 mm typed as 1 rejected with mm hint; grams-as-kg flagged; calibration finish blocked on bad fit naming worst point; blank diameter blocked or noted; tests"
bound = false
+++
