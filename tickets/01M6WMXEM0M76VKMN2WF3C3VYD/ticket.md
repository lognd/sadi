+++
id = "01M6WMXEM0M76VKMN2WF3C3VYD"
title = "Wire a real CurveSource (active session events) into create_app for stress-strain fit"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:58:26Z"
updated = "2026-11-08T04:01:33Z"
scope = ["python/sadi/server/**", "python/tests/server/test_curve_source.py", "docs/server/app.md"]

[[acceptance]]
text = "With no injected curve_source, create_app serves POST /api/stress-strain/fit from the newest session under data_root, and returns 409 NoData when none exists"
bound = true

[[acceptance]]
text = "Reading the active session never writes or modifies any file in it"
bound = true
+++

found while working ~V69GETD: endpoint takes an injected curve_source; no production source builds CurvePoints from session events (see labs/lctt/export_csv.build_document). Request has no session id, so an active-session concept is needed. Until wired the route returns 409 NoData.
