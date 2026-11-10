+++
id = "01M72V8SNA08E3QD12A1TSFDV3"
title = "Live/open-session payloads and exports must report unknown provenance (resumed unknown session)"
type = "bug"
category = "todo"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T13:44:56Z"
updated = "2026-11-10T13:44:56Z"
scope = ["python/sadi/server/service.py", "python/sadi/server/routes/export.py", "python/tests/server/test_readonly_export.py"]

[[acceptance]]
text = "Open session resumed from an unknown-provenance session reports unknown in live payloads and open-session exports; never real"
bound = false
+++
