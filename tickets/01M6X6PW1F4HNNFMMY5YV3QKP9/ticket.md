+++
id = "01M6X6PW1F4HNNFMMY5YV3QKP9"
title = "Wizard has no step that captures the specimen; LCTT CSV export 422 NotReady"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T09:09:25Z"
updated = "2026-11-08T09:27:19Z"
scope = ["web/src/**", "python/sadi/server/**", "python/sadi/core/wizard.py", "python/tests/core/test_wizard.py", "web/e2e/**", "docs/README.md", "docs/api", "docs/architecture.md", "docs/bench", "docs/ci.md", "docs/concurrency-testing.md", "docs/concurrency.md", "docs/core", "docs/data-safety.md", "docs/device", "docs/doctor-checks.md", "docs/doctor.md", "docs/domain.md", "docs/e2e.md", "docs/hardware", "docs/hardware-verification.md", "docs/index.md", "docs/jobs", "docs/lctt", "docs/live-view.md", "docs/open-questions.md", "docs/packaging.md", "docs/plan.md", "docs/plugins.md", "docs/portability.md", "docs/protocol-vectors.json", "docs/protocol.md", "docs/publishing.md", "docs/python-layout.md", "docs/release.md", "docs/rust-type-design.md", "docs/sadi-proto.md", "docs/server", "docs/store", "docs/testing.md", "docs/uncertainty", "docs/user-guide.md", "docs/ux.md"]
+++

found while working ~WV4W4WY: POST /api/session/points phase=specimen is rejected (no_capture / phase_mismatch) at every wizard step, so GET /api/export/lctt-csv cannot succeed in a guided run; guided-run.spec.ts omits the CSV download until fixed.
