+++
id = "01M6W7R1HWQMSEX38TQM27Y4NY"
title = "Significant-figure and confidence-readout formatter (class rule)"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 3
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:23:50Z"
idempotency_key = "sadi-sf1"
labels = ["ws:py", "oq:Q13", "model:sonnet", "creates:python/sadi/core/formatting.py", "creates:python/tests/core/test_formatting.py", "creates:docs/core/formatting.md"]
scope = ["python/sadi/core/formatting.py", "python/tests/core/test_formatting.py", "docs/core/formatting.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R13KW0FFYHZJ7FY28A3R"

[[acceptance]]
text = "format_result(value, u) -> 'v +/- U unit' with 3 s.f. result and 2 s.f. uncertainty, rounding rules for leading-1 cases documented, engineering/scientific notation choice, SI prefixes; sig-fig counts configurable"
bound = true

[[acceptance]]
text = "plain_language_confidence(value, u95, target) -> short sentence (e.g. 'E is known to within 4.2 % at 95 % confidence; target 5 % reached')"
bound = true

[[acceptance]]
text = "Table-driven tests incl. zero, negative, tiny/huge, U larger than value"
bound = true
+++

Default 3 s.f./2 s.f. from the class rule; rubric (open question Q13) may adjust, so counts are config.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
