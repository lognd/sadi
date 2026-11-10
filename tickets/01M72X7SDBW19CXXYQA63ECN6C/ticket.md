+++
id = "01M72X7SDBW19CXXYQA63ECN6C"
title = "Automatic error propagation for the weight plan and results (mass, diameter, L0, volts to stress, strain, E, yield)"
type = "story"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T14:19:20Z"
updated = "2026-11-10T14:28:47Z"
labels = ["creates:python/sadi/labs/lctt/propagate.py", "creates:python/tests/labs/lctt/test_propagate.py", "creates:docs/uncertainty/weight-plan.md"]
scope = ["python/sadi/labs/lctt/propagate.py", "python/tests/labs/lctt/test_propagate.py", "docs/uncertainty/weight-plan.md", "docs/uncertainty/budget.md", "changelog.d/01M72X7SDBW19CXXYQA63ECN6C.added.md"]

[[acceptance]]
text = "Using sadi.uncertainty Measured/budget, a function takes inventory weight uncertainties, diameter, L0, calibration and voltage noise and returns stress, strain, E and yield each with standard uncertainty, 95 percent interval and a per-input contribution budget; GUM linear result agrees with the Monte Carlo result within tolerance in a test; the same function is used for plan predictions and for captured data so there is one code path; Result errors, logging"
bound = true
+++

User request: propagate error automatically. Reuse python/sadi/uncertainty (symbolic, budget, montecarlo); check what sadi/labs/lctt/modulus.py and live.py already propagate and extract rather than copy. Do not alter stored data.
