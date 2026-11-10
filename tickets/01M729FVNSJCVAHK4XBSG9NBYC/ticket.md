+++
id = "01M729FVNSJCVAHK4XBSG9NBYC"
title = "audit4 L3+L4+L5+L7: phase hints, session facts refresh, sticky offset, SYNTHETIC badge, RECOVERED export"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-10T08:34:13Z"
updated = "2026-11-10T08:41:34Z"
labels = ["audit4"]
scope = ["web/src/screens/run/phases.ts", "web/src/hooks/useStickyOffset.ts", "web/src/screens/setup/SessionSetup.tsx", "python/sadi/server/routes/export.py", "web/src/components/instrument/useBackendFacts.ts", "web/src/components/instrument/FactsContext.tsx", "web/src/components/wizard/CloseSession.tsx", "web/src/hooks/useStickyOffset.test.ts", "web/src/screens/setup/SessionSetup.test.tsx", "python/tests/server/test_readonly_export.py", "web/src/screens/run/RunScreen.test.tsx", "web/src/App.tsx", "web/src/styles.css", "docs/ux.md", "docs/synthetic.md"]

[[acceptance]]
text = "Phase hints match auto-open; No session clears right after create/close; sticky offset does not override media rule; SessionSetup shows SYNTHETIC badge; torn-tail export has RECOVERED- prefix and # RECOVERED: line"
bound = true
+++
