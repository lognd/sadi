+++
id = "01M6X1GGD923K25M13JM84ZB2J"
title = "app: no API/UI to mark a load change, so the live point never settles (guided-run e2e fails at [Settled])"
type = "bug"
category = "in-progress"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-08T07:38:34Z"
updated = "2026-11-08T07:43:52Z"
scope = ["python/sadi/server/**", "python/tests/server/**", "python/tests/cli/**"]

[[acceptance]]
text = "POST /api/session/load-change records a WAL marker and 409s with no live session; Run screen has a Mark load change button; guided-run e2e passes"
bound = false
+++

found while working ~F4YK7XN: the stream now flows, but nothing calls AcquisitionPipeline.mark_load_change (no server route, no web call), so the settle detector stays at loading and the readout never shows [Settled]. web/e2e/guided-run.spec.ts fails at acceptWhenSettled; run-capture specs skip.
