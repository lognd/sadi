+++
id = "01M6W7Y4Z2K9JGX7ZGJQH52HR2"
title = "Add Status header lines to pre-existing docs (DOC003)"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T00:11:38Z"
updated = "2026-11-08T00:25:07Z"
scope = ["docs/domain.md", "docs/open-questions.md", "docs/plan.md", "docs/preliminary-data-analysis.md", "docs/protocol.md"]

[[acceptance]]
text = "Given the five docs listed in scope, when frob check --ticket runs, then no DOC003 finding is reported for any of them"
bound = false
+++

found while working ~1DQHSR7: DOC003 fires on 5 pre-existing docs lacking a Status: line
