+++
id = "01M6ZYR3NCDB0G8XHP86JCZFDM"
title = "docs: organize into one grouped index (merge README.md and index.md)"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-09T10:48:00Z"
updated = "2026-11-09T10:50:55Z"
idempotency_key = "docs-organize-index"
scope = ["docs/index.md", "docs/README.md"]

[[acceptance]]
text = "docs/index.md lists every docs/**/*.md exactly once in grouped sections; README.md points to it; no relative link broken"
bound = true
+++
