+++
id = "01M6WRR08HNAKHCT71WW0VNNSP"
title = "numeric central difference raises ZeroDivisionError for subnormal step"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T05:05:22Z"
updated = "2026-11-08T05:06:55Z"
scope = ["python/sadi/uncertainty/numeric.py", "python/tests/uncertainty/test_fallbacks.py"]

[[acceptance]]
text = "Subnormal x (5e-324) no longer raises ZeroDivisionError in central_difference"
bound = true

[[acceptance]]
text = "A zero or non-representable step returns a typed Err instead of raising"
bound = true
+++

found while working ~2C5G9GB: tests/uncertainty/test_fallbacks.py::test_central_difference_matches_cubic_derivative fails with hypothesis example a=0.0,b=0.0,x=5e-324 (ZeroDivisionError at numeric.py:148).
