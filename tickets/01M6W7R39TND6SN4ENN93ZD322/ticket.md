+++
id = "01M6W7R39TND6SN4ENN93ZD322"
title = "GP selector implementation and benchmark vs baselines"
type = "task"
category = "todo"
priority = "high"
points = 8
parent = "01M6W7R081S67XNGBH79ACCBZZ"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T00:08:20Z"
idempotency_key = "sadi-gp2"
labels = ["ws:plan", "model:sonnet", "creates:python/sadi/core/planning/gp.py", "creates:python/sadi/core/planning/stopping.py", "creates:python/tests/core/planning/test_gp.py", "creates:docs/core/planning-gp.md"]
scope = ["python/sadi/core/planning/gp.py", "python/sadi/core/planning/stopping.py", "python/tests/core/planning/test_gp.py", "docs/core/planning-gp.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1PV3YSB3EKX6K80WDK8"

[[links]]
kind = "blocked-by"
target = "01M6W7R2WARAR5FD127S5YPBEJ"

[[acceptance]]
text = "suggest_next(phase, observations, candidates, target) -> Result[Suggestion(weights, expected_gain, predicted_halfwidth)]; recommendation object {halfwidth, target, enough: bool, reason}"
bound = false

[[acceptance]]
text = "Benchmark test on simulator: reaches target CI half-width in fewer points than random and binary-search baselines in >= 80% of seeds (documented numbers)"
bound = false

[[acceptance]]
text = "Out-of-range heights never suggested; no suggestion when no candidate adds information"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
