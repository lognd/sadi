+++
id = "01M72TJ0CQPCRKAW2EWSFP9Y8Z"
title = "Provenance 'unknown' source for orphan spill imports (no SYNTHETIC label/filename)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T13:32:29Z"
updated = "2026-11-10T13:42:28Z"
scope = ["python/sadi/synthetic/provenance.py", "python/sadi/store/spill.py", "web/src/api/schema.ts", "python/sadi/**", "python/tests/**", "web/src/**", "docs/synthetic.md"]

[[acceptance]]
text = "Orphan import is neither real nor synthetic; export filename and UI say unknown; openapi and schema.ts regenerated"
bound = true
+++
