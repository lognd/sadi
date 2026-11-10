+++
id = "01M72YAG5JF05K4W68BCPGKVGP"
title = "Load points carry voltage uncertainty U=2*sd (parity M1) and operator/description in CSV header (parity L1)"
type = "story"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T14:38:18Z"
updated = "2026-11-10T15:25:57Z"
labels = ["creates:python/tests/labs/lctt/test_load_unc_header.py"]
scope = ["web/src/screens/run/live.ts", "python/sadi/labs/lctt/lab.py", "python/sadi/server/service.py", "python/sadi/server/routes/export.py", "python/sadi/core/models.py", "python/sadi/labs/lctt/export_csv.py", "web/src/screens/setup/SessionSetup.tsx", "web/src/screens/run/inputFields.ts", "python/tests/labs/lctt/test_load_unc_header.py", "web/src/screens/run/live.test.ts", "docs/lctt/export-csv.md", "web/src/screens/run/inputFields.test.ts"]

[[acceptance]]
text = "Load points post volts_sd/u_volts; CSV header has operator and description."
bound = true
+++

See parity.md in scratchpad. Blocked by uncommitted edits to live.ts and lab.py.
