+++
id = "01M6W7R3BBDEXG9CPYWTQ7ZKZW"
title = "LCTT E fit (selectable window), r^2, secant E, yield, saturation warning"
type = "task"
category = "in-progress"
priority = "high"
points = 8
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T03:15:37Z"
idempotency_key = "sadi-a3"
labels = ["ws:py", "lctt", "oq:Q3", "model:sonnet", "creates:python/sadi/labs/lctt/modulus.py", "creates:python/sadi/labs/lctt/yield_.py", "creates:python/sadi/labs/lctt/saturation.py", "creates:python/tests/labs/lctt/test_modulus.py", "creates:docs/lctt/modulus.md"]
scope = ["python/sadi/labs/lctt/modulus.py", "python/sadi/labs/lctt/yield_.py", "python/sadi/labs/lctt/saturation.py", "python/tests/labs/lctt/test_modulus.py", "docs/lctt/modulus.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1RD3P97HFFDZ2NVD83Y"

[[links]]
kind = "blocked-by"
target = "01M6W7R2BS0R89GW39HM0XPX0J"

[[links]]
kind = "blocked-by"
target = "01M6W7R2XY9DB0PFREY9TZ8D2S"

[[acceptance]]
text = "E fit over a selectable window of points (default manual first/last per Q3, optional auto-window suggestion as a hint only) returning E, standard error, U95, r^2, n; per-point secant E"
bound = true

[[acceptance]]
text = "0.2 % offset yield stress with uncertainty; ultimate stress; flags windows with r^2 below configurable threshold"
bound = true

[[acceptance]]
text = "Saturation: any |V| > 4.9 raises a typed warning flag on the point (threshold config; discrepancy 4.8/4.9/5.12 documented)"
bound = false

[[acceptance]]
text = "Report records which settle value (settled window, forced-early, fixed-dwell) fed each point used in the E fit"
bound = false

[[acceptance]]
text = "E and yield formulas are plain @uncertain functions; the uncertainty budget (U4) for E is exposed through the results model"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
