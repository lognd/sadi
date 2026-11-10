+++
id = "01M700BKP28566PCN32SS9BY5N"
title = "ci: typani lint TYP004 propagation findings (69) across store, server, cli, doctor"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-09T11:16:08Z"
updated = "2026-11-09T11:28:52Z"
scope = ["python/sadi/**"]

[[acceptance]]
text = "Given the sadi package, when python -m typani.lint sadi runs, then it reports no TYP004 findings and the store, concurrency and full pytest suites pass"
bound = true
+++
