+++
id = "01M6WZCNF9F9XSPWCKB34JHSD9"
title = "Mount wizard shell and run/review/export screens in App.tsx"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-08T07:01:31Z"
updated = "2026-11-08T07:05:49Z"
scope = ["web/src/App.tsx", "web/src/main.tsx", "web/src/screens/**", "web/src/components/wizard/**", "web/src/App*.tsx", "web/e2e/**", "docs/e2e.md", "docs/web/**"]

[[acceptance]]
text = "App mounts the wizard shell and run/review/export screens with the step rail visible, Doctor reachable"
bound = true
+++

found while working ~GW7ER11: App only renders health page and Doctor; guided-run e2e specs skip until mounted
