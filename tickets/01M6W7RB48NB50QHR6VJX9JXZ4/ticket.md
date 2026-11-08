+++
id = "01M6W7RB48NB50QHR6VJX9JXZ4"
title = "Wheels and release workflow with install smoke test (maturin, 3 OS)"
type = "chore"
category = "in-progress"
priority = "medium"
points = 5
parent = "01M6W7R00Z87A80RZB3JCC7HDM"
reporter = "lognd"
created = "2026-11-08T00:08:28Z"
updated = "2026-11-08T05:49:39Z"
idempotency_key = "sadi-c2"
labels = ["ws:ci", "model:sonnet", "creates:.github/workflows/wheels.yml", "creates:docs/release.md"]
scope = [".github/workflows/wheels.yml", "docs/release.md", "python/tests/packaging/test_wheels_workflow.py", "python/pyproject.toml"]

[[links]]
kind = "blocked-by"
target = "01M6W7R226VMAMHYPDBQTAS277"

[[links]]
kind = "blocked-by"
target = "01M6W7RAFMFB5NMWGZY0VYJVFZ"

[[links]]
kind = "blocked-by"
target = "01M6W7RAW944RFCMESYZKJSYXC"

[[acceptance]]
text = "maturin builds sadi-py wheels for linux (manylinux), windows, macOS (x86_64 + arm64); pure-Python sadi wheel bundles the built UI"
bound = false

[[acceptance]]
text = "Smoke job: fresh venv, pip install wheel, `sadi --version`, `sadi --sim --no-browser --selftest` exits 0 on all 3 OS"
bound = false

[[acceptance]]
text = "docs/release.md documents the release procedure"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
