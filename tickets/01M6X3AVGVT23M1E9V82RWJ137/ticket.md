+++
id = "01M6X3AVGVT23M1E9V82RWJ137"
title = "Capture and wizard complete latency grows with WAL size; e2e guided run times out (wait_durable fails under sim load)"
type = "bug"
category = "todo"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-08T08:10:26Z"
updated = "2026-11-08T08:12:59Z"
scope = ["python/sadi/server/**"]
+++

found while working ~PQBZCCN: service._act replays the whole WAL twice per action; with the simulator writing ~200k raw records per minute, POST /api/session/points goes 3s, 5s, 13s, 30s+, wizard/complete never returns, and the writer logs wait_durable failed 'data disk is not responding' (durable_seq lags enqueued_seq). web/e2e/guided-run.spec.ts cannot finish Setup->Export. Needs incremental replay state and/or a bounded sim write rate.
