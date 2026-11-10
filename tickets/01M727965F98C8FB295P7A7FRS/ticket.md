+++
id = "01M727965F98C8FB295P7A7FRS"
title = "M5+M6: latest-version by lineage; download torn-tail sessions"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T07:55:38Z"
updated = "2026-11-10T08:02:31Z"
labels = ["creates:python/tests/server/test_latest_lineage.py"]
scope = ["python/sadi/server/routes/sessions.py", "python/sadi/server/service.py", "web/src/screens/setup/SessionSetup.tsx", "python/sadi/server/routes/export.py", "web/src/screens/setup/SessionSetup.test.tsx", "python/tests/server/test_readonly_export.py", "python/tests/server/test_latest_lineage.py"]

[[acceptance]]
text = "latest computed by parent ancestry excluding incomplete; interrupted/incomplete sessions downloadable as verified prefix with X-SADI-Torn-Tail header; Download shown for them; tests"
bound = true
+++
