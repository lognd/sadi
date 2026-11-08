+++
id = "01M6W7R2A727G6H66B6FBSDE1R"
title = 'Fallbacks: numeric-derivative path and Monte Carlo path (method="mc")'
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R0EPXRHEMNEAB9QWVY57"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T01:23:16Z"
idempotency_key = "sadi-u3"
labels = ["ws:unc", "uncertainty", "model:sonnet", "creates:python/sadi/uncertainty/numeric.py", "creates:python/sadi/uncertainty/montecarlo.py", "creates:python/tests/uncertainty/test_fallbacks.py", "creates:docs/uncertainty/fallbacks.md"]
scope = ["python/sadi/uncertainty/numeric.py", "python/sadi/uncertainty/montecarlo.py", "python/tests/uncertainty/test_fallbacks.py", "docs/uncertainty/fallbacks.md", "python/sadi/uncertainty/uncertain.py", "docs/uncertainty/uncertain.md", "python/sadi/uncertainty/__init__.py", "python/tests/uncertainty/test_uncertain.py"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1RD3P97HFFDZ2NVD83Y"

[[acceptance]]
text = 'For functions sympy cannot trace (branches, numpy calls): documented numeric-derivative path (complex-step where valid, else adaptive central differences with step control) selected automatically or via method="numeric"'
bound = true

[[acceptance]]
text = '`method="mc"` via the same decorator: seeded vectorised Monte Carlo sampling from the full covariance (multivariate normal; documented non-Gaussian options), returns mean, sd, 95% interval; sample generator is resumable so jobs (J3) can refine progressively'
bound = true

[[acceptance]]
text = "Cross-check helper flags disagreement between analytic, numeric and MC beyond tolerance"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
