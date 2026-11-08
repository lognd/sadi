+++
id = "01M6W7R0HZCA3MXA7231DQHSR7"
title = "Architecture doc, repo layout and docs index"
type = "docs"
category = "done"
outcome = "done"
priority = "high"
points = 3
parent = "01M6W7R00Z87A80RZB3JCC7HDM"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:11:40Z"
idempotency_key = "sadi-d0"
labels = ["ws:docs", "model:sonnet", "creates:docs/architecture.md", "creates:docs/README.md"]
scope = ["docs/architecture.md", "docs/README.md"]

[[acceptance]]
text = "docs/architecture.md defines process model (browser <-> FastAPI <-> sadi_py <-> sadi-proto <-> Transport), repo layout (crates/, python/, web/), session directory layout, error-handling convention (Rust Result -> exception at PyO3 boundary -> typani Result in Python -> HTTP problem JSON)"
bound = true

[[acceptance]]
text = "docs/README.md indexes every doc and states the rule that each change updates its doc"
bound = true

[[acceptance]]
text = "Lists which ticket owns which docs file (see docs/plan.md)"
bound = true
+++

Foundation doc every other ticket cites. Fixes interfaces so workstreams can run in parallel. Blocked by open question: none (defaults from docs/open-questions.md Q1, Q2 are user-confirmed: both live DAQ + post-processing, 32-column VI).

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
