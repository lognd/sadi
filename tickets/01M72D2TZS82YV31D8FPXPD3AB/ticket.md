+++
id = "01M72D2TZS82YV31D8FPXPD3AB"
title = "Spill import: join on real fsync failure, safe supersede, provenance, bounded copy"
type = "bug"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T09:37:01Z"
updated = "2026-11-10T12:32:31Z"
scope = ["python/sadi/store/spill.py", "python/sadi/server/routes/sessions.py", "docs/store/spill.md", "python/sadi/store/manifest.py", "python/tests/server/test_latest_lineage.py", "python/tests/store/test_spill.py", "python/sadi/server/schemas.py", "python/sadi/server/service.py", "web/src/api/openapi.json"]

[[acceptance]]
text = "M1 overlap join verified by real WalWriter + wal.fsync.before test"
bound = true

[[acceptance]]
text = "M2 only joined closed import supersedes incomplete parent"
bound = true

[[acceptance]]
text = "M3 import inherits synthetic; orphan conservative"
bound = true

[[acceptance]]
text = "M4 free-space check + failed-import marker"
bound = true

[[acceptance]]
text = "L2 original seqs kept or followup ticket"
bound = true
+++
