+++
id = "01M6Z3FR6FP6TTP9BW4MHJSE85"
title = "FakeDwf supports only SINGLE acquisition: no continuous streaming for AD3 LCTT E2E"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-09T02:51:35Z"
updated = "2026-11-09T03:08:44Z"
scope = ["python/sadi/bench/ad3/fake.py", "python/tests/bench/test_ad3_fake.py", "docs/bench/ad3.md", "changelog.d/*MHJSE85*"]

[[acceptance]]
text = "Given FakeDwf in RECORD/SCAN mode, when polled with read_data, then TRIGGERED and phase-continuous blocks are latched"
bound = true
+++

found while working GHQ8PEY
