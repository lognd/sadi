+++
id = "01M700BKR5MEDX30NV79VV5628"
title = "ci: e2e fails, sadi_py not importable in the sadi server subprocess (macOS/Windows)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-09T11:16:08Z"
updated = "2026-11-09T11:19:24Z"
scope = [".github/workflows/e2e.yml", "web/e2e/fixtures.ts"]

[[acceptance]]
text = "given sadi_py built by the e2e workflow, when uv run --no-sync launches sadi --sim, then sadi_py imports"
bound = true
+++
