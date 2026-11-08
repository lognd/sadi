+++
id = "01M6W7RB2G5W6WPWDRKJS6PJJY"
title = "User guide: running a test with the app (procedure, two specimens, creep)"
type = "docs"
category = "in-progress"
priority = "low"
points = 3
parent = "01M6W7R00Z87A80RZB3JCC7HDM"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T05:56:43Z"
idempotency_key = "sadi-doc1"
labels = ["ws:docs", "model:sonnet", "creates:docs/user-guide.md", "creates:docs/img/ui/**"]
scope = ["docs/user-guide.md", "docs/img/ui/**", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3RXWS1WSH3TPXMK16Q2"

[[links]]
kind = "blocked-by"
target = "01M6W7R3TJETR6N3EVA9PMPWH8"

[[links]]
kind = "blocked-by"
target = "01M6W7RAFMFB5NMWGZY0VYJVFZ"

[[links]]
kind = "blocked-by"
target = "01M6W7RAPKVH796SZ6Z9EFDXQE"

[[acceptance]]
text = "Step-by-step bench procedure mapping to docs/domain.md section 6, including clamp-slip pre-check, calibration, tare, hold/confirm, review, export"
bound = false

[[acceptance]]
text = "States which settle value feeds the E fit and how to override it"
bound = false

[[acceptance]]
text = "Screenshots under docs/img/ui/"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
