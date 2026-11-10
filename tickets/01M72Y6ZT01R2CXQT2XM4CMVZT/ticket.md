+++
id = "01M72Y6ZT01R2CXQT2XM4CMVZT"
title = "WAL segment roll forces full-WAL rebase under the service lock; all session routes hang (audit8 H1)"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T14:36:23Z"
updated = "2026-11-10T14:37:16Z"
labels = ["creates:python/tests/store/test_incremental_roll.py"]
scope = ["python/sadi/store/incremental.py", "python/sadi/store/snapshot.py", "python/sadi/server/service.py"]

[[acceptance]]
text = "After a segment roll IncrementalReplay.state() does not rebase and equals a full replay; _snapshot after a roll does not call prefix_hash; prefix_hashes_at stops at max covers_seq."
bound = false
+++

Details and fix direction (a)-(e) in /tmp/claude-1000/-home-logan-projects-SADI/4f193782-dc1d-4c66-a170-89d2ce998f4d/scratchpad/audit8.md section H1. Test with a small segment_max_bytes.
