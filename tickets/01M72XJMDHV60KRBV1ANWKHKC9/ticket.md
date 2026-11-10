+++
id = "01M72XJMDHV60KRBV1ANWKHKC9"
title = "Record a large raw-sample block per tare/capture and store mean, sd, n (like the VI 2500-sample block)"
type = "story"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T14:25:16Z"
updated = "2026-11-10T15:20:00Z"
labels = ["creates:tests/labs/lctt/test_block_capture.py"]
scope = ["python/sadi/labs/lctt/capture.py", "python/sadi/server/live.py", "web/src/screens/run/live.ts", "web/src/screens/run/inputFields.ts", "python/sadi/server/service.py", "python/sadi/server/app.py", "python/sadi/server/schemas.py", "docs/user-guide.md", "python/tests/labs/lctt/test_block_capture.py", "web/src/screens/run/inputFields.test.ts"]

[[acceptance]]
text = "Tare and calibration capture average a fixed large block of RAW samples (default 2500, configurable) on the server, not the 1 s decimated columns in the browser; the stored point carries mean, sample sd and n; the UI shows n and refuses a capture below the minimum n; uncertainty is sd/sqrt(n) combined with instrument accuracy"
bound = true
+++
