+++
id = "01M6Z3FR48WS686Q8Z52SQ2BN8"
title = "AD3 LCTT hardware: SADI read-back over serial facade for ad3_hw tests (scope ch0 is supply monitor)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-09T02:51:35Z"
updated = "2026-11-09T03:18:08Z"
scope = ["python/tests/bench/test_lctt_ad3_hw.py", "python/sadi/bench/sadi_readback.py", "docs/bench/lctt-ad3-matrix.md", "docs/bench/ad3.md", "python/tests/bench/test_sadi_readback.py"]

[[acceptance]]
text = "ad3_hw tests read DC levels back from the SADI board over the serial facade and assert the AD3 scope supply monitor reads ~3.3 V"
bound = true
+++

found while working GHQ8PEY
