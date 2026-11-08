+++
id = "01M6W7RAW944RFCMESYZKJSYXC"
title = "Packaging: bundle built UI into the sadi wheel, entry points"
type = "chore"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T05:45:57Z"
idempotency_key = "sadi-pk1"
labels = ["ws:srv", "model:sonnet", "creates:python/sadi/_ui/.gitkeep", "creates:packaging/build_ui.py", "creates:docs/packaging.md"]
scope = ["python/sadi/_ui/.gitkeep", "packaging/build_ui.py", "docs/packaging.md", "python/sadi/launcher.py", "python/tests/cli/test_launcher_ui.py", "python/tests/packaging/**", "python/pyproject.toml", ".gitignore", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0R9PGCDJWAD321F3H53"

[[links]]
kind = "blocked-by"
target = "01M6W7RAFMFB5NMWGZY0VYJVFZ"

[[acceptance]]
text = "Build step runs vite build and copies dist into the Python package data; wheel contains the UI and `sadi` console script"
bound = false

[[acceptance]]
text = "Documented one-command build; works from a clean checkout on all 3 OS"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
