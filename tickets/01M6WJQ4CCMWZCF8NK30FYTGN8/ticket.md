+++
id = "01M6WJQ4CCMWZCF8NK30FYTGN8"
title = "Overflow in propagation leaks exceptions: pydantic ValidationError (analytic) and OverflowError (numeric) from _derive/effective_dof"
type = "bug"
category = "in-progress"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-08T03:20:02Z"
updated = "2026-11-08T03:23:20Z"
scope = ["python/sadi/uncertainty/measured.py", "python/sadi/uncertainty/coverage.py", "python/tests/uncertainty/crosscheck/test_labs_crosscheck.py", "docs/uncertainty/crosscheck.md"]
+++

found while working ~QTA833F. For stress/strain with strain ~1e-80..1e-200, analytic path raises ValidationError (std_unc=inf in Measured) and numeric path raises OverflowError in coverage.effective_dof (u_i**2). Both should return a typed UncertaintyError (DomainError/InvalidUncertainty). Repro: Uncertain(lambda a,b:a/b)(Measured.create(1,.01), Measured.create(8.7e-80,8.7e-82)).
