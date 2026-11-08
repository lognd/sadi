+++
id = "01M6W7R1883HHXY4XYEJA5DMTN"
title = "store/durable: cross-OS fsync, dir-fsync, atomic replace, exclusive create"
type = "task"
category = "done"
outcome = "done"
priority = "critical"
points = 5
parent = "01M6W7R04QJTECCTSV9EY2JADK"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:30:45Z"
idempotency_key = "sadi-ds2"
labels = ["ws:store", "model:sonnet", "creates:python/sadi/store/durable.py", "creates:python/tests/store/test_durable.py", "creates:docs/store/durable.md"]
scope = ["python/sadi/store/durable.py", "python/tests/store/test_durable.py", "docs/store/durable.md", "python/sadi/store/__init__.py", "python/sadi/store/failpoints.py", "python/tests/store/test_failpoints.py", "python/tests/store/__init__.py", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0PMCGFDSFY53XDK2EVN"

[[links]]
kind = "blocked-by"
target = "01M6W7R0T0AC47BJGF2CKTER59"

[[acceptance]]
text = "fsync_file, fsync_dir (no-op where unsupported, documented), create_exclusive (O_CREAT|O_EXCL / CREATE_NEW), atomic_replace(tmp, dst) with fsync of data then dir, F_FULLFSYNC on macOS, WRITE_THROUGH on Windows; all return typani Result"
bound = true

[[acceptance]]
text = "Failpoint hooks (env/registry) per DS1 so DS6 can kill between steps"
bound = true

[[acceptance]]
text = "Unit tests run on all 3 OS in CI; Windows sharing-violation retry covered by test with a held handle"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
