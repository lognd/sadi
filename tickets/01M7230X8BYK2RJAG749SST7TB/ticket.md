+++
id = "01M7230X8BYK2RJAG749SST7TB"
title = "Audit2 H1: pace --sim device to real time; cap ws state messages (server hangs)"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T06:41:12Z"
updated = "2026-11-10T06:49:45Z"
labels = ["creates:python/tests/server/test_sim_pacing.py"]
scope = ["python/sadi/server/live.py", "python/sadi/server/ws.py", "python/sadi/core/pipeline.py", "docs/server/api.md", "docs/server/app.md", "docs/server/export.md", "docs/server/inventory.md", "docs/server/launcher.md", "docs/server/plots.md", "docs/server/results-stream.md", "docs/server/results.md", "docs/server/websocket.md", "python/tests/server/test_sim_pacing.py", "python/sadi/core/device.py", "python/tests/server/test_ws.py"]

[[acceptance]]
text = "sim source paced at device rate; ws state coalesced to <=30Hz; test shows /api/health <100ms with ws client on --sim"
bound = true
+++
