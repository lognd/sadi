+++
id = "01M709MS0TBDHNX4HSVFD80SXV"
title = "docs: core/device.md reader queue default is now 4096 blocks"
type = "bug"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-09T13:58:26Z"
updated = "2026-11-10T02:44:16Z"
scope = ["docs/core/device.md"]

[[acceptance]]
text = "Given docs/core/device.md, when read, then the reader queue default matches DEFAULT_QUEUE_BLOCKS (4096)"
bound = true
+++

found while working 01M709DXGS91GPWZ3M06FWXJPY; docs/core/device.md says default 256 blocks, leased by N6VY4KP
