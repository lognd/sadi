+++
id = "01M6WNV0R4RXDTR3JBBESM525T"
title = "COV001: store/events.py settings_record reached by no test"
type = "bug"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T04:14:35Z"
updated = "2026-11-08T04:17:25Z"
scope = ["python/sadi/store/**", "python/tests/store/test_events.py"]

[[acceptance]]
text = "settings_record is reached by a bound test"
bound = true
+++

found while working ~QXARDHK: frob check flags settings_record as reached by no test; bind with frob:tests. Blocks land via E-LAND-CHECK-RED.
