+++
id = "01M71SKWW36NDBJK24QD7DHSW4"
title = "Web: always-on instrument bar, debug strip, and newcomer-proof pages"
type = "story"
category = "todo"
priority = "medium"
points = 8
reporter = "lognd"
created = "2026-11-10T03:56:48Z"
updated = "2026-11-10T03:56:50Z"
scope = ["web/src/**", "docs/web/**"]

[[acceptance]]
text = "Instrument bar (large live LVDT volts, displacement/load when calibrated, drift, settle, connection, sim banner) renders on EVERY page including pre-session Setup, at the top, with no scrolling"
bound = false

[[acceptance]]
text = "Debug strip shows device/firmware, sample rate, seq/durable seq, frame age, backend state, session id, data-root, save/WAL state, last error, all visible at a glance"
bound = false

[[acceptance]]
text = "Landing/session-setup page explains the tension test in plain language, has labelled well-spaced form, and Results/error states show plain-language messages (no raw enum reprs)"
bound = false

[[acceptance]]
text = "vitest, tsc, eslint, crunk check pass; docs/web updated"
bound = false
+++
