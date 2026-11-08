+++
id = "01M6XAZ42NR9WARFYVZMS85NR2"
title = "Web: regenerate schema.ts and POST run-phase on wizard phase transitions"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T10:23:50Z"
updated = "2026-11-08T10:26:25Z"
scope = ["docs/web/wizard.md", "web/src/api/runPhase.test.ts", "web/src/api/runPhase.ts", "web/src/api/schema.ts", "web/src/screens/WizardHost.tsx"]

[[acceptance]]
text = "Wizard POSTs /api/session/run-phase on calibrate->elastic->plastic transitions; schema.ts regenerated; vitest covers it"
bound = true
+++
