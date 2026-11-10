+++
id = "01M72D2TZS82YV31D8FPXPD3AB"
title = "Spill import: join on real fsync failure, safe supersede, provenance, bounded copy"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T09:37:01Z"
updated = "2026-11-10T09:37:04Z"
scope = ["python/sadi/store/spill.py", "python/sadi/server/routes/sessions.py", "python/tests/**/*spill*", "python/tests/**/*sessions*", "docs/store/spill.md"]

[[acceptance]]
text = "M1 overlap join verified by real WalWriter + wal.fsync.before test"
bound = false

[[acceptance]]
text = "M2 only joined closed import supersedes incomplete parent"
bound = false

[[acceptance]]
text = "M3 import inherits synthetic; orphan conservative"
bound = false

[[acceptance]]
text = "M4 free-space check + failed-import marker"
bound = false

[[acceptance]]
text = "L2 original seqs kept or followup ticket"
bound = false
+++
