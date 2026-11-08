+++
id = "01M6W7RBBF0Y5QQVH34W5XJBZT"
title = "Usability pass: scripted walkthrough, issue log and fixes"
type = "task"
category = "in-progress"
priority = "medium"
points = 5
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:28Z"
updated = "2026-11-08T09:58:55Z"
idempotency_key = "sadi-f14"
labels = ["ws:web", "usability", "model:sonnet", "creates:docs/usability-report.md", "creates:web/src/screens/**/*.usability.md"]
scope = ["docs/usability-report.md", "web/src/screens/**/*.usability.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R432XQSR47M3W61M215J"

[[links]]
kind = "blocked-by"
target = "01M6W7RAMTFXRP2FHAFAEZAQ6K"

[[links]]
kind = "blocked-by"
target = "01M6W7RARKCF5E5N60RFHNEDX8"

[[links]]
kind = "blocked-by"
target = "01M6W7RB7ZFKF3DVKWW74FQXWT"

[[links]]
kind = "blocked-by"
target = "01M6W7RB9Q00GBJ5CJ0GW7ER11"

[[acceptance]]
text = "Run the F0 usability protocol (cold start to exported CSV in the simulator within the time budget; keyboard-only run) and record issues with severity"
bound = true

[[acceptance]]
text = "All severity-1 issues fixed or ticketed; report committed to docs/usability-report.md"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
