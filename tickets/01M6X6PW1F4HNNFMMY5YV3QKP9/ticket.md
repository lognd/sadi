+++
id = "01M6X6PW1F4HNNFMMY5YV3QKP9"
title = "Wizard has no step that captures the specimen; LCTT CSV export 422 NotReady"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T09:09:25Z"
updated = "2026-11-08T09:27:11Z"
scope = ["web/src/**", "python/sadi/server/**", "python/sadi/core/wizard.py"]
+++

found while working ~WV4W4WY: POST /api/session/points phase=specimen is rejected (no_capture / phase_mismatch) at every wizard step, so GET /api/export/lctt-csv cannot succeed in a guided run; guided-run.spec.ts omits the CSV download until fixed.
