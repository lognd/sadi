+++
id = "01M727TR8PNCVA3CA5ZAVFBREF"
title = "L3+L5: debug strip shows faulted device as ok; SEQ/DURABLE mix WS and WAL seq"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T08:05:13Z"
updated = "2026-11-10T08:09:18Z"
labels = ["creates:web/src/components/debug/DebugStrip.test.tsx"]
scope = ["python/sadi/server/routes/results.py", "web/src/components/instrument/DebugStrip.tsx", "python/tests/server/test_results_routes.py", "docs/ux.md", "web/src/components/debug/DebugStrip.test.tsx"]

[[acceptance]]
text = "Faulted device renders as fault, not [ok]; SEQ and DURABLE are labelled and sourced from one seq space"
bound = true
+++
