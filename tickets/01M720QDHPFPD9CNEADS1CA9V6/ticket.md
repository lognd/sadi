+++
id = "01M720QDHPFPD9CNEADS1CA9V6"
title = "Audit1 #4 #2 #21: wire Save/WAL indicator to real writer; provenance for --sim; manifest/WAL-based synthetic provenance"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T06:01:04Z"
updated = "2026-11-10T06:09:57Z"
scope = ["python/sadi/launcher.py", "python/sadi/server/app.py", "python/sadi/store/session.py", "python/tests/server/**", "python/tests/store/**", "python/tests/cli/test_launcher_live.py", "docs/server/app.md", "docs/synthetic.md"]

[[acceptance]]
text = "Save indicator reflects the real WAL writer (not always Saved); --sim runs are labelled simulated, not real; session_is_synthetic reads manifest/WAL, not only the sidecar; tests prove each"
bound = false
+++
