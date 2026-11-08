+++
id = "01M6X06TPZ3W86FDHQPX01MME8"
title = "Launcher registers no labs: GET /api/labs is empty so no session can be created"
type = "bug"
category = "todo"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-08T07:15:48Z"
updated = "2026-11-08T07:17:21Z"
scope = ["python/sadi/launcher.py"]
+++

found while working ~E2BTRN2: launcher.main builds AppSettings(data_root, device) without labs, so LabRegistry is empty and the Setup screen cannot create a session (e2e guided-run/run-capture skip). Wire LabRegistry.from_plugins(builtin plugins) into AppSettings.
