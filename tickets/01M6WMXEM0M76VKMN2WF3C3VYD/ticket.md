+++
id = "01M6WMXEM0M76VKMN2WF3C3VYD"
title = "Wire a real CurveSource (active session events) into create_app for stress-strain fit"
type = "bug"
category = "todo"
priority = "medium"
reporter = "lognd"
created = "2026-11-08T03:58:26Z"
updated = "2026-11-08T03:58:26Z"
scope = ["python/sadi/server/**"]
+++

found while working ~V69GETD: endpoint takes an injected curve_source; no production source builds CurvePoints from session events (see labs/lctt/export_csv.build_document). Request has no session id, so an active-session concept is needed. Until wired the route returns 409 NoData.
