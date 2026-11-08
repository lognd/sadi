+++
id = "01M6W7R1PV3YSB3EKX6K80WDK8"
title = "GP / sequential-design selector: design doc (information gain, stop rule)"
type = "docs"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R081S67XNGBH79ACCBZZ"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:48:45Z"
idempotency_key = "sadi-gp1"
labels = ["ws:plan", "design", "model:fable", "creates:docs/gp-selector.md"]
scope = ["docs/gp-selector.md", "docs/README.md", "docs/plan.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0HZCA3MXA7231DQHSR7"

[[links]]
kind = "blocked-by"
target = "01M6W7R155JD0XGVXHDSP19B1H"

[[acceptance]]
text = "Formulates the three phase problems (LVDT calibration, elastic fit, plastic/yield) as sequential design: parameter posterior (Bayesian linear / GP on the response), acquisition = expected reduction in target CI half-width (D/A-optimal or integrated variance), candidate set from WS1"
bound = true

[[acceptance]]
text = "Specifies the stop-early recommendation: criterion on CI half-width vs user target with a patience rule, always advisory; and the 'confidence is enough' indicator payload"
bound = true

[[acceptance]]
text = "Defines handling of drift/creep (settled-only observations), non-linearity near yield, cold start with few points, computational budget (<200 ms per suggestion), determinism and a simulator-based benchmark protocol versus random and binary-search baselines"
bound = true
+++

Fable ticket. The user always makes the stop call; the selector only recommends.

Suggested model: Fable.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
