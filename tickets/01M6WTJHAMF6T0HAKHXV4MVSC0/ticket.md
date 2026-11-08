+++
id = "01M6WTJHAMF6T0HAKHXV4MVSC0"
title = "docs: update server api.md resume bullet (parent state is now folded, ~S7757MP)"
type = "task"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T05:37:20Z"
updated = "2026-11-08T05:42:14Z"
labels = ["modifies:docs/server/api.md"]
scope = ["docs/server/api.md"]

[[acceptance]]
text = "Resume folds the parent's POINT, EDIT, SETTINGS and MARKER records into the child WAL and the parent stays byte-identical (docs/server/api.md Data safety)"
bound = true
+++

The Data safety resume bullet in docs/server/api.md still says the new version starts a fresh WAL and the parent state is not folded in. ~S7757MP landed folding; update the text. Start after ~4QRM2GS releases its lease on that file.
