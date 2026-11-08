+++
id = "01M6W7R13KW0FFYHZJ7FY28A3R"
title = "core models: pydantic domain models and error taxonomy"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:19:23Z"
idempotency_key = "sadi-p2"
labels = ["ws:py", "model:sonnet", "creates:python/sadi/core/models.py", "creates:python/sadi/core/errors.py", "creates:python/tests/core/test_models.py", "creates:docs/core/models.md"]
scope = ["python/sadi/core/models.py", "python/sadi/core/errors.py", "python/tests/core/test_models.py", "docs/core/models.md", "docs/README.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0HZCA3MXA7231DQHSR7"

[[links]]
kind = "blocked-by"
target = "01M6W7R0PMCGFDSFY53XDK2EVN"

[[acceptance]]
text = "Pydantic models: Quantity(value, standard_uncertainty, unit), Weight(id, mass, u_mass, height, u_height), WeightInventory, GroupWeighing, Specimen, CapturedPoint(window, t_since_load, drift_rate, settled|forced_early, edits), Phase, RunState; JSON round-trip tested"
bound = true

[[acceptance]]
text = "Error enums (frozen dataclasses/pydantic) for use as typani E types; each carries a user-facing 'what to do' hint"
bound = true

[[acceptance]]
text = "Units are SI internally; unit conversion only at display"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
