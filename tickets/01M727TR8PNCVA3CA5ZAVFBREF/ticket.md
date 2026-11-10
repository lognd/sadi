+++
id = "01M727TR8PNCVA3CA5ZAVFBREF"
title = "L3+L5: debug strip shows faulted device as ok; SEQ/DURABLE mix WS and WAL seq"
type = "bug"
category = "todo"
priority = "medium"
reporter = "lognd"
created = "2026-11-10T08:05:13Z"
updated = "2026-11-10T08:05:13Z"
labels = ["creates:web/src/components/debug/DebugStrip.test.tsx"]
scope = ["web/src/components/debug/DebugStrip.tsx", "python/sadi/server/routes/results.py"]

[[acceptance]]
text = "Faulted device renders as fault, not [ok]; SEQ and DURABLE are labelled and sourced from one seq space"
bound = false
+++
