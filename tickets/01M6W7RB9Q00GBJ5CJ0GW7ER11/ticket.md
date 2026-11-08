+++
id = "01M6W7RB9Q00GBJ5CJ0GW7ER11"
title = "Browser e2e (Playwright) on 3 OS: full guided run against the simulator"
type = "task"
category = "in-progress"
priority = "medium"
points = 5
parent = "01M6W7R0D1R7J4VQJVKGX8YEZ9"
reporter = "lognd"
created = "2026-11-08T00:08:28Z"
updated = "2026-11-08T06:57:21Z"
idempotency_key = "sadi-t2"
labels = ["ws:qa", "model:sonnet", "creates:web/e2e/**", "creates:.github/workflows/e2e.yml", "creates:docs/e2e.md"]
scope = ["web/e2e/**", ".github/workflows/e2e.yml", "docs/e2e.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7RAFMFB5NMWGZY0VYJVFZ"

[[links]]
kind = "blocked-by"
target = "01M6W7RARKCF5E5N60RFHNEDX8"

[[links]]
kind = "blocked-by"
target = "01M6W7RATGKGPEYSMC5H8WGMBV"

[[links]]
kind = "blocked-by"
target = "01M6W7RB7ZFKF3DVKWW74FQXWT"

[[acceptance]]
text = "Playwright drives `sadi --sim` through Setup -> Export using only the keyboard; asserts results panel values, CSV export, PNG figure export non-empty"
bound = false

[[acceptance]]
text = "Runs on ubuntu, windows, macos in e2e.yml"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
