+++
id = "01M6WKWJ9BAHV3YM2PXJFZJFBF"
title = "Link docs/server/app.md from docs/index.md with an index test"
type = "chore"
category = "in-progress"
priority = "low"
points = 1
reporter = "lognd"
created = "2026-11-08T03:40:29Z"
updated = "2026-11-08T03:40:57Z"
scope = ["docs/index.md", "python/tests/test_docs_index.py"]

[[acceptance]]
text = "docs/index.md links server/app.md and web/results-panel.md, guarded by index tests"
bound = true

[[acceptance]]
text = "pytest tests/test_docs_index.py passes"
bound = true
+++
