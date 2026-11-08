+++
id = "01M6W7R3N96SVM2D2GQQTA833F"
title = "Uncertainty cross-check suite on every lab formula (analytic vs MC vs finite difference)"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R0EPXRHEMNEAB9QWVY57"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T03:20:40Z"
idempotency_key = "sadi-u5"
labels = ["ws:unc", "qa", "model:sonnet", "creates:python/tests/uncertainty/crosscheck/**", "creates:docs/uncertainty/crosscheck.md"]
scope = ["python/tests/uncertainty/crosscheck/**", "docs/uncertainty/crosscheck.md", "docs/uncertainty/fallbacks.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R2A727G6H66B6FBSDE1R"

[[links]]
kind = "blocked-by"
target = "01M6W7R2BS0R89GW39HM0XPX0J"

[[links]]
kind = "blocked-by"
target = "01M6W7R3BBDEXG9CPYWTQ7ZKZW"

[[acceptance]]
text = "Parametrised test over every @uncertain lab formula (calibration, load from mass, stress, strain, E, fits): analytic vs MC vs finite difference agree within documented tolerances, with and without correlation"
bound = false

[[acceptance]]
text = "Hypothesis-generated inputs including near-zero denominators produce typed errors, not exceptions"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
