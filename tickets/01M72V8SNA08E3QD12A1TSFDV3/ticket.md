+++
id = "01M72V8SNA08E3QD12A1TSFDV3"
title = "Live/open-session payloads and exports must report unknown provenance (resumed unknown session)"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T13:44:56Z"
updated = "2026-11-10T13:49:30Z"
scope = ["python/sadi/server/service.py", "python/sadi/server/routes/export.py", "python/tests/server/test_readonly_export.py", "python/sadi/server/ws.py", "python/sadi/server/routes_stress_strain.py", "python/sadi/server/app.py", "docs/synthetic.md"]

[[acceptance]]
text = "Open session resumed from an unknown-provenance session reports unknown in live payloads and open-session exports; never real"
bound = true
+++
