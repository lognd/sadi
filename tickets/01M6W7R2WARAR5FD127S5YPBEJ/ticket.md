+++
id = "01M6W7R2WARAR5FD127S5YPBEJ"
title = "Weight-sequence generator: combinations, binary-search-like, filtering"
type = "task"
category = "done"
outcome = "wont-fix"
priority = "high"
points = 8
parent = "01M6W7R081S67XNGBH79ACCBZZ"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T02:27:18Z"
idempotency_key = "sadi-ws1"
labels = ["ws:plan", "oq:Q7", "oq:Q8", "model:sonnet", "creates:python/sadi/core/planning/sequence.py", "creates:python/tests/core/planning/test_sequence.py", "creates:docs/core/sequence.md"]
scope = ["python/sadi/core/planning/sequence.py", "python/tests/core/planning/test_sequence.py", "docs/core/sequence.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R26WGJ0TZ4GS8N0YH4FG"

[[acceptance]]
text = "Enumerates achievable stack heights/masses from numbered weights incl. combinations and duplicates (multiple copies, swapped weights between calibration and experiment), propagating uncertainty via the inventory"
bound = false

[[acceptance]]
text = "Candidate generator for phase (a) heights: binary-search-like coverage of the LVDT range; automatically filters out-of-range heights (LVDT +-4.9 V / 20 mm travel, wire length) and useless points (duplicates within resolution, points that add < epsilon information)"
bound = false

[[acceptance]]
text = "Outputs ordered candidate steps as 'use weights 3, 5, 6' with expected height/load; tested for no out-of-range output and minimality"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
