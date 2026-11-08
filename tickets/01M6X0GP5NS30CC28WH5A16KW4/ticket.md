+++
id = "01M6X0GP5NS30CC28WH5A16KW4"
title = "e2e: Enter on Setup (Clamp slip check) does not advance the wizard against the launcher-built app"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T07:21:11Z"
updated = "2026-11-08T07:31:31Z"
scope = ["python/pyproject.toml", "python/uv.lock", "web/e2e/**", "web/src/components/wizard/**"]

[[acceptance]]
text = "PUT wizard complete/skip POSTs carry the current step as a JSON body so Enter and Skip advance the wizard against the launcher-built app"
bound = true
+++
