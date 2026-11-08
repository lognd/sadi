+++
id = "01M6WMSZKN488HTWG19V69GETD"
title = "Add POST /api/stress-strain/fit refit endpoint"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:56:33Z"
updated = "2026-11-08T03:57:32Z"
scope = ["python/sadi/server/**", "python/tests/server/**", "docs/server/*.md"]
+++

found while working ~D754A8M: web client api/refit.ts expects POST /api/stress-strain/fit {first,last} -> ModulusFitView (first,last,modulusMpa,interceptMpa,eGpa,eU95Gpa,r2,lowR2). No such route exists.
