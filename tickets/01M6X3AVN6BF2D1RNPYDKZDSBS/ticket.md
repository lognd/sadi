+++
id = "01M6X3AVN6BF2D1RNPYDKZDSBS"
title = "e2e specs share one backend session: a failed spec poisons the next (run-capture second test skipped)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-08T08:10:26Z"
updated = "2026-11-08T08:34:15Z"
scope = ["web/e2e/**", "docs/e2e.md"]

[[acceptance]]
text = "Each e2e test runs against its own backend (fresh temp data dir and port) so specs start at Setup"
bound = true
+++

found while working ~PQBZCCN: openWizard resumes the existing session when the server is shared, so run-capture specs start mid-run (e.g. at Tare) and get skipped or fail. Needs a fresh data dir/session per spec (or per-test server).
