+++
id = "01M72T4R3X8833V8Z978SH4481"
title = "Spill import: verify before close, fragment fallback on verify failure, lineage through fragments, orphan provenance"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T13:25:15Z"
updated = "2026-11-10T13:27:21Z"
labels = ["creates:none"]
scope = ["python/sadi/store/spill.py", "python/sadi/server/routes/sessions.py", "python/tests/store/test_spill.py", "python/tests/server/test_latest_lineage.py", "web/src/screens/setup/SessionSetup.tsx", "docs/store/spill.md"]

[[acceptance]]
text = "Verify failure -> crashed + failed marker + fragment import; in-progress sidecar prevents repeat copies; fragment->resume keeps parent as latest; orphan provenance unknown not synthetic; SessionSetup labels fragment/joined; tests incl. a6 repros. No data deleted."
bound = false
+++

Audit6 M3,M4,L2. _import_version closes before verify and retries copying each start; _descendants walks through fragment kids making full parent read superseded; orphan spills labelled SYNTHETIC; SessionSetup does not label fragment/joined.
