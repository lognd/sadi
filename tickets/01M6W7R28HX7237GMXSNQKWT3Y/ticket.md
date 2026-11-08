+++
id = "01M6W7R28HX7237GMXSNQKWT3Y"
title = "LCTT calibration: LINEST-equivalent fit with standard errors and t95"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T01:09:15Z"
idempotency_key = "sadi-a1"
labels = ["ws:py", "lctt", "oq:Q6", "model:sonnet", "creates:python/sadi/labs/lctt/calibration.py", "creates:python/tests/labs/lctt/test_calibration.py", "creates:docs/lctt/calibration.md"]
scope = ["python/sadi/labs/lctt/calibration.py", "python/tests/labs/lctt/test_calibration.py", "docs/lctt/calibration.md", "docs/core/lab-modules.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R13KW0FFYHZJ7FY28A3R"

[[links]]
kind = "blocked-by"
target = "01M6W7R155JD0XGVXHDSP19B1H"

[[links]]
kind = "blocked-by"
target = "01M6W7R1RD3P97HFFDZ2NVD83Y"

[[acceptance]]
text = "Linear fit volts->height returning slope, intercept, their standard errors, covariance, r^2, dof, t95 half-widths, residuals, CI band function; matches the oracle expected values to 6 digits for the short-run calibration"
bound = true

[[acceptance]]
text = "Height-input uncertainty and voltage uncertainty enter via U1 (errors-in-both option); only slope feeds strain, intercept reported as offset (Q6)"
bound = true

[[acceptance]]
text = "Result is typani Result: too few points, degenerate x, rank deficiency"
bound = true

[[acceptance]]
text = "Calibration formulas are plain functions decorated with @uncertain (written once); slope/intercept covariance feeds downstream via Measured"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
