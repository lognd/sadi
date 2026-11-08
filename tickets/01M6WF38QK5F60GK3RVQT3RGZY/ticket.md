+++
id = "01M6WF38QK5F60GK3RVQT3RGZY"
title = "Flaky: test_property_slope_recovered_within_standard_error fails in full suite"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T02:16:46Z"
updated = "2026-11-08T03:29:51Z"
scope = ["python/tests/labs/lctt/test_calibration.py"]

[[acceptance]]
text = "Test passes reliably in full suite"
bound = true

[[acceptance]]
text = "Property tests bound the estimated-SE error with the Student-t quantile (not a normal 6-sigma) and are derandomized"
bound = true
+++
