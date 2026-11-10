+++
id = "01M7274EH583A30335TGGT6ZZ1"
title = "M1+M2: show stop_reason banner and add Reconnect button in instrument bar"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T07:53:02Z"
updated = "2026-11-10T07:55:42Z"
labels = ["creates:web/src/components/instrument/StopBanner.tsx", "creates:web/src/components/instrument/StopBanner.test.tsx"]
scope = ["web/src/components/instrument/", "web/src/api/"]

[[acceptance]]
text = "Banner from device.stop_reason/acquisition_fault shown regardless of source, per-reason plain-language next steps; Reconnect button POSTs /api/device/reconnect when status disconnected/error, disables while pending, shows hint; signal shows No data when frameAgeMs null; vitest tests; no data loss"
bound = true
+++
