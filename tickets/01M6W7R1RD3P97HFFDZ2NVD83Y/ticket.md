+++
id = "01M6W7R1RD3P97HFFDZ2NVD83Y"
title = "@uncertain decorator: sympy tracing, lambdify, full-covariance RSS, .symbolic/.latex/.partials"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 8
parent = "01M6W7R0EPXRHEMNEAB9QWVY57"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:31:44Z"
idempotency_key = "sadi-u2"
labels = ["ws:unc", "uncertainty", "model:sonnet", "creates:python/sadi/uncertainty/uncertain.py", "creates:python/sadi/uncertainty/symbolic.py", "creates:python/sadi/uncertainty/cache.py", "creates:python/tests/uncertainty/test_uncertain.py", "creates:docs/uncertainty/uncertain.md"]
scope = ["python/sadi/uncertainty/uncertain.py", "python/sadi/uncertainty/symbolic.py", "python/sadi/uncertainty/cache.py", "python/tests/uncertainty/test_uncertain.py", "docs/uncertainty/uncertain.md", "python/sadi/uncertainty/__init__.py", "docs/uncertainty/measured.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R155JD0XGVXHDSP19B1H"

[[acceptance]]
text = "`@uncertain` takes an ordinary plain-math function over Measured args, traces it symbolically with sympy, derives partials, lambdifies to numpy, caches per function (and per arg dimension), returns a Measured"
bound = true

[[acceptance]]
text = "Propagation uses the FULL covariance matrix u^2 = J C J^T, including correlation between inputs such as calibration slope and intercept; test proves ignoring correlation gives a different (wrong) answer on a correlated case"
bound = true

[[acceptance]]
text = "Exposes `.symbolic` (sympy expr), `.latex` (render of formula and derivation), `.partials`, `.sensitivities(...)`; units checked at the decorator boundary"
bound = true

[[acceptance]]
text = "Untraceable functions return an error value pointing to the fallback paths (U3); never raises in user-facing paths"
bound = true

[[acceptance]]
text = "Importable alongside typani: `from typani import propagate` and `from sadi.uncertainty import uncertain` coexist; no public name equals a typani export; hypothesis tests vs closed forms"
bound = true
+++

Dependency on sympy goes in python/pyproject.toml (owned by P1; widen lease).

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
