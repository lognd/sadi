+++
id = "01M6W7R1VQHABR51SH64668M06"
title = "store/wal: append-only checksummed fsynced writer, reader, recovery"
type = "task"
category = "done"
outcome = "done"
priority = "critical"
points = 8
parent = "01M6W7R04QJTECCTSV9EY2JADK"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:44:35Z"
idempotency_key = "sadi-ds3"
labels = ["ws:store", "model:sonnet", "creates:python/sadi/store/wal.py", "creates:python/sadi/store/records.py", "creates:python/tests/store/test_wal.py", "creates:docs/store/wal.md"]
scope = ["python/sadi/store/wal.py", "python/sadi/store/records.py", "python/tests/store/test_wal.py", "docs/store/wal.md", "python/pyproject.toml", "python/uv.lock", "python/sadi/store/__init__.py", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0T0AC47BJGF2CKTER59"

[[links]]
kind = "blocked-by"
target = "01M6W7R1883HHXY4XYEJA5DMTN"

[[acceptance]]
text = "WalWriter.append(record) -> Result[Seq, WalError]; group commit per DS1; durable_seq advances only after fsync; rotation with directory fsync"
bound = true

[[acceptance]]
text = "Throughput test: sustains 612 kB/s plus markers with p99 append latency documented"
bound = true

[[acceptance]]
text = "Property tests: random truncation and bit flips never yield an accepted corrupt record"
bound = true

[[acceptance]]
text = "WalReader iterates verified records and stops at the verified prefix; a torn tail is reported (offset, length, SHA-256) and NEVER truncated or modified (docs/data-safety.md: resume opens a new version dir); a bad CRC mid-log is rejected and reported, never silently skipped"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
