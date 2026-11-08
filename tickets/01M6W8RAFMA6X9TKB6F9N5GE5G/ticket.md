+++
id = "01M6W8RAFMA6X9TKB6F9N5GE5G"
title = "docs: python-layout.md store path disagrees with DS2-DS8 scopes"
type = "bug"
category = "done"
outcome = "done"
priority = "low"
points = 1
reporter = "lognd"
created = "2026-11-08T00:25:55Z"
updated = "2026-11-08T02:03:03Z"
scope = ["docs/python-layout.md"]

[[acceptance]]
text = "docs/python-layout.md names the store package sadi/store/ (python/sadi/store/), matching DS2-DS8 scopes, data-safety.md and the on-disk layout"
bound = true

[[acceptance]]
text = "The package ownership table row for the store reads sadi/store/"
bound = true
+++

found while working ~CKTER59: docs/python-layout.md places the store under sadi/core/store/ while the DS2-DS8 ticket scopes and docs/data-safety.md use python/sadi/store/. Align the layout doc with the tickets.
