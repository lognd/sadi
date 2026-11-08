+++
id = "01M6X04JE0EPAKEGK7N2FFGCDZ"
title = "Web: App probes missing /api/health, so Doctor always opens against the real backend"
type = "bug"
category = "done"
outcome = "wont-fix"
priority = "high"
reporter = "lognd"
created = "2026-11-08T07:14:34Z"
updated = "2026-11-08T07:18:58Z"
scope = ["web/src/App.tsx", "web/src/api/client.ts"]
+++

found while working ~E2BTRN2: getHealth GETs /api/health which the backend does not serve (404), so openDoctorOnConnectionError hides the wizard on every load. Either add the route or probe /openapi.json. e2e helper closes Doctor as a workaround.
