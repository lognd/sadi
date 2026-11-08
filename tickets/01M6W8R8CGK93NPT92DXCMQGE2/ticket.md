+++
id = "01M6W8R8CGK93NPT92DXCMQGE2"
title = "docs: add Status: header line to five pre-existing docs (DOC003)"
type = "bug"
category = "done"
outcome = "done"
priority = "low"
points = 1
reporter = "lognd"
created = "2026-11-08T00:25:53Z"
updated = "2026-11-08T02:02:32Z"
scope = ["docs/domain.md", "docs/open-questions.md", "docs/plan.md", "docs/preliminary-data-analysis.md", "docs/protocol.md"]

[[acceptance]]
text = "Each of the five scoped docs has a Status: line in its header block (DOC003 clean)"
bound = true

[[acceptance]]
text = "preliminary-data-analysis.md is marked draft, not current, because its data is unvalidated"
bound = true
+++

found while working ~CKTER59: frob check reports DOC003 (no Status: line in the header block) on docs/domain.md, docs/open-questions.md, docs/plan.md, docs/preliminary-data-analysis.md and docs/protocol.md on main.
