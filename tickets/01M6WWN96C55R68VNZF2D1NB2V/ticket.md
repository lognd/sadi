+++
id = "01M6WWN96C55R68VNZF2D1NB2V"
title = "Run screen: F3 export from the run trace"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T06:13:47Z"
updated = "2026-11-08T06:23:17Z"
scope = ["web/src/screens/run/**", "docs/web/run-screens.md"]

[[acceptance]]
text = "F3 on the run screen downloads GET /api/export/{format} (default lctt-csv) via resolveKey"
bound = false

[[acceptance]]
text = "Export failures surface as a status message"
bound = false
+++

found while working ~74FQXWT
