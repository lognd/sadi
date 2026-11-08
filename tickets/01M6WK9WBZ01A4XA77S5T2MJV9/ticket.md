+++
id = "01M6WK9WBZ01A4XA77S5T2MJV9"
title = "Crosscheck: test_near_zero_denominator_is_typed_not_raised[numeric] fails on main (x=1e-300 divisor, complex-step partial 1e+300)"
type = "bug"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-08T03:30:17Z"
updated = "2026-11-08T03:32:57Z"
scope = ["python/sadi/uncertainty/numeric.py", "python/sadi/uncertainty/measured.py", "python/tests/uncertainty/crosscheck/test_labs_crosscheck.py", "docs/uncertainty/numeric.md", "python/sadi/uncertainty/montecarlo.py", "docs/uncertainty/fallbacks.md"]

[[acceptance]]
text = "Near-zero denominators (1e-300) give a typed Err on numeric and mc paths with no raise and no RuntimeWarning"
bound = true
+++
