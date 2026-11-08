+++
id = "01M6W7R16PR162ZWC8EM7BT5SB"
title = "CI matrix: Windows, Linux, macOS (Rust, Python, web)"
type = "chore"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R00Z87A80RZB3JCC7HDM"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:32:53Z"
idempotency_key = "sadi-c1"
labels = ["ws:ci", "model:sonnet", "creates:.github/workflows/ci.yml", "creates:docs/ci.md"]
scope = [".github/workflows/ci.yml", "docs/ci.md", "docs/web-layout.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0KH8QFP4K9PTM197V9E"

[[links]]
kind = "blocked-by"
target = "01M6W7R0PMCGFDSFY53XDK2EVN"

[[links]]
kind = "blocked-by"
target = "01M6W7R0R9PGCDJWAD321F3H53"

[[acceptance]]
text = "Matrix ubuntu-latest, windows-latest, macos-latest runs: cargo fmt --check, clippy -D warnings, cargo test; ruff, python -m typani.lint, type check, pytest; web lint, tsc, vitest, vite build"
bound = true

[[acceptance]]
text = "Caches (cargo, uv, npm); required-check names documented in docs/ci.md"
bound = true

[[acceptance]]
text = "Crash-recovery and e2e jobs live in their own workflow files (DS6, T2) and are listed as required checks in docs/ci.md"
bound = true

[[acceptance]]
text = "CI lint step runs tools/check_typani_collisions.py (U6)"
bound = true
+++

Cross-OS CI from day one; portability bugs (fsync/rename, paths, serial names) must fail early. Scope also owns docs/ci.md.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
