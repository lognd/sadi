+++
id = "01M6W7R155JD0XGVXHDSP19B1H"
title = "sadi.uncertainty core: Measured value type, covariance, units, provenance"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 8
parent = "01M6W7R0EPXRHEMNEAB9QWVY57"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:21:00Z"
idempotency_key = "sadi-u1"
labels = ["ws:unc", "uncertainty", "model:sonnet", "creates:python/sadi/uncertainty/__init__.py", "creates:python/sadi/uncertainty/measured.py", "creates:python/sadi/uncertainty/covariance.py", "creates:python/sadi/uncertainty/units.py", "creates:python/sadi/uncertainty/errors.py", "creates:python/sadi/uncertainty/coverage.py", "creates:python/tests/uncertainty/test_measured.py", "creates:docs/uncertainty/measured.md"]
scope = ["python/sadi/uncertainty/__init__.py", "python/sadi/uncertainty/measured.py", "python/sadi/uncertainty/covariance.py", "python/sadi/uncertainty/units.py", "python/sadi/uncertainty/errors.py", "python/sadi/uncertainty/coverage.py", "python/tests/uncertainty/test_measured.py", "docs/uncertainty/measured.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0PMCGFDSFY53XDK2EVN"

[[acceptance]]
text = "pydantic `Measured`: value, standard uncertainty, optional covariance/correlation with other Measured (shared covariance registry keyed by id), unit, provenance (source event/WAL seq or derivation name); arithmetic operators propagate through the same machinery as @uncertain; JSON round-trip"
bound = true

[[acceptance]]
text = "Units and dimensional checking via pint (or documented equivalent): mismatched dimensions return an error value, never raise in user-facing paths; SI internally"
bound = true

[[acceptance]]
text = "Coverage utilities: t95 from dof, 95% interval, relative uncertainty, effective dof (Welch-Satterthwaite)"
bound = true

[[acceptance]]
text = "Public API avoids typani names (typani exports propagate, catching, Result, Ok, Err, unwrap, ErrorSet, UnwrapError; the uncertainty package must not reuse these names); a test module imports `from typani import propagate` and `from sadi.uncertainty import uncertain` together with no alias or shadowing"
bound = true

[[acceptance]]
text = "All fallible functions return typani Results with typed error enums carrying a 'what to do' hint; hypothesis property tests"
bound = true
+++

Foundation of the uncertainty engine. Inputs are entered once (weight inventory, instrument uncertainties); every downstream quantity is derived so the user never re-enters a number. Naming: package `sadi.uncertainty`, decorator `uncertain` (never `propagate`).

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
