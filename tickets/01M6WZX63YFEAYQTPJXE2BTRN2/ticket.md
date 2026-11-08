+++
id = "01M6WZX63YFEAYQTPJXE2BTRN2"
title = "Web: Setup screen that creates or resumes a session (WizardHost shows nothing when no session is open)"
type = "bug"
category = "todo"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-08T07:10:32Z"
updated = "2026-11-08T07:10:32Z"
+++

Found running web/e2e against sim: GET /api/session returns 409 no_open_session and the UI never offers to open one, so the wizard never appears. Needs a Setup screen: list GET /api/sessions (resumable, incl. recovered), POST /api/sessions/resume, POST /api/sessions (new, specimen/lab inputs). Never overwrite or auto-discard an existing session; confirm before anything destructive.
