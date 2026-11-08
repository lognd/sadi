+++
id = "01M6WMSZKN488HTWG19V69GETD"
title = "Add POST /api/stress-strain/fit refit endpoint"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:56:33Z"
updated = "2026-11-08T03:58:51Z"
scope = ["python/sadi/server/**", "python/tests/server/**", "docs/server/*.md"]

[[acceptance]]
text = "POST /api/stress-strain/fit {first,last} returns ModulusFitView fields in client units"
bound = false

[[acceptance]]
text = "Bad window or no data returns a typed 4xx {error,detail}; endpoint never writes"
bound = false
+++

found while working ~D754A8M: web client api/refit.ts expects POST /api/stress-strain/fit {first,last} -> ModulusFitView (first,last,modulusMpa,interceptMpa,eGpa,eU95Gpa,r2,lowR2). No such route exists.
