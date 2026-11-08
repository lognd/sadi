+++
id = "01M6W7R26WGJ0TZ4GS8N0YH4FG"
title = "Weight inventory with uncertainty and group balance weighing"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T01:15:08Z"
idempotency_key = "sadi-wi1"
labels = ["ws:py", "oq:Q7", "model:sonnet", "creates:python/sadi/core/inventory.py", "creates:python/tests/core/test_inventory.py", "creates:docs/core/inventory.md"]
scope = ["python/sadi/core/inventory.py", "python/tests/core/test_inventory.py", "docs/core/inventory.md", "docs/core/lab-modules.md"]

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
text = "User enters numbered weights (1,2,3,...) with mass, mass uncertainty, height and height uncertainty once; stored as WAL events (editable, history kept)"
bound = true

[[acceptance]]
text = "Group balance weighing (instructor note): mass of a named subset weighed together with its uncertainty; the inventory reconciles it with individual masses (combined estimate, consistency warning) and any combination mass/uncertainty/height is derived automatically, with correlated group terms handled"
bound = true

[[acceptance]]
text = "combo(weight_ids) -> Quantity mass, Quantity stack height via U1; tested incl. group vs individual defence (Q7)"
bound = true
+++

Open question Q7 (balance group vs individual) default: support both, prefer the lower-uncertainty estimate and show the choice.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
