+++
id = "01M6WV6TH775MHY7HHMND4Z97Z"
title = "Real-browser 60 fps benchmark for live trace"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T05:48:25Z"
updated = "2026-11-08T05:58:42Z"
scope = ["web/src/plots/live/**"]

[[acceptance]]
text = "Pure frame-time statistics helpers are unit tested"
bound = false

[[acceptance]]
text = "Opt-in frame benchmark harness exists, is tested with a fake clock, and docs state the 60 fps result is UNVERIFIED"
bound = false
+++

found while working 7KWS2S7
