+++
id = "01M7230XGWSR1B8D93KW5M4P7D"
title = "Audit2 H2/H5 web: Close session and Start another controls; CSV download via fetch with error and saved message"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T06:41:12Z"
updated = "2026-11-10T06:44:46Z"
scope = ["web/src/screens/WizardHost.tsx", "web/src/screens/export/ExportScreen.test.tsx", "web/src/screens/export/ExportScreen.tsx", "web/src/screens/export/ExportScreen.usability.md", "web/src/screens/export/api.ts", "web/src/screens/export/figureScenes.ts", "web/src/screens/export/types.ts", "web/src/components/budget", "web/src/components/guidance", "web/src/components/instrument", "web/src/components/live", "web/src/components/provenance", "web/src/components/results", "web/src/components/shell", "web/src/components/status", "web/src/components/wizard", "web/src/api/client.test.ts", "web/src/api/client.ts", "web/src/api/log.test.ts", "web/src/api/log.ts", "web/src/api/openapi.json", "web/src/api/refit.test.ts", "web/src/api/refit.ts", "web/src/api/result.ts", "web/src/api/runPhase.test.ts", "web/src/api/runPhase.ts", "web/src/api/schema.test.ts", "web/src/api/schema.ts"]

[[acceptance]]
text = "finished screen and header have Close session; export download shows problem detail on non-2xx and Saved-copy message; vitest proves each"
bound = false
+++
