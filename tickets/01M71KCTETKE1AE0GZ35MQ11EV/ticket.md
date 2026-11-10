+++
id = "01M71KCTETKE1AE0GZ35MQ11EV"
title = "GP weight selector: GpLoadSuggester wired into LCTT guidance"
type = "task"
category = "in-progress"
priority = "high"
points = 8
reporter = "lognd"
created = "2026-11-10T02:08:05Z"
updated = "2026-11-10T02:12:25Z"
labels = ["model:sonnet", "creates:python/sadi/labs/lctt/gp_suggester.py", "creates:python/tests/labs/lctt/test_gp_suggester.py", "creates:docs/labs/lctt-gp-selector.md"]
scope = ["python/sadi/labs/lctt/guidance.py", "python/tests/labs/lctt/test_guidance.py", "python/sadi/labs/lctt/gp_suggester.py", "python/tests/labs/lctt/test_gp_suggester.py", "docs/labs/lctt-gp-selector.md", "docs/index.md"]

[[acceptance]]
text = "GpLoadSuggester implements LoadSuggester: picks the candidate load (from the feasible weight combos in the LoadRange) maximising expected reduction of modulus-slope CI half-width (linear/elastic, rank-one update, weak prior) and uses a Matern/RBF GP over (load, displacement) for the plastic phase; cold start (<3 points) falls back to extremes then bisection; deterministic, ties to lowest index"
bound = false

[[acceptance]]
text = "guide() uses GpLoadSuggester by default for the elastic and plastic phases, falling back to EvenScheduleSuggester on Err; GuidanceState gains expected_gain, expected_half_width, alternatives (top 3 loads) and gp_state fields (optional, backward compatible)"
bound = false

[[acceptance]]
text = "Tests: beats even-schedule and random in fewer points to reach target half-width on seeded synthetic data; never suggests outside the range; deterministic; docs/labs/lctt-gp-selector.md documents the maths and fields. Design reference (read only, do not import): private/final-project/docs/gp-selector.md"
bound = false
+++

Implement the Gaussian-process weight (load) selection the user asked for for the LCTT tensile test. Advisory only: the user decides the load. Standards: ASCII only, no emojis, NEVER a Co-Authored-By line; module logger never print; one-line docstring on public symbols; typani Result for fallible ops; update docs in the same change; tests in the same change; tracked code must not import or link private/ or labview/. Heavy builds via goway.
