+++
id = "01M6WJQ4A9Q9MTK0XQQSJ9VQC9"
title = "numeric fallback step floor (_scale >= 1) crosses poles for SI-small inputs; NoConvergence on x/y"
type = "bug"
category = "in-progress"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-08T03:20:02Z"
updated = "2026-11-08T03:22:29Z"
scope = ["python/sadi/uncertainty/numeric.py", "python/tests/uncertainty/**"]

[[acceptance]]
text = "Given gradient(a/b) at b=1e-3, when computed numerically, then it converges and SI stress cross-check passes"
bound = true
+++

found while working ~QTA833F. numeric._scale floors the Ridders start step at 1e-2, so for |x|<1 (strain 0.004, area 1.2e-4, all SI lab inputs) the step crosses the pole of a/x: central_difference returns NoConvergence, so gradient() and method='numeric'/auto fallback/cross_check fail for stress, secant_modulus, chord_modulus, yield_*. Repro: gradient(lambda a,b: a/b, [1.0, 1e-3]). Fix: step relative to |x| (fall back to 1.0 only when x==0).
