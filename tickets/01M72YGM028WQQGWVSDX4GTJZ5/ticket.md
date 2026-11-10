+++
id = "01M72YGM028WQQGWVSDX4GTJZ5"
title = "WAL rebase leftovers: store NOTE payloads in snapshot, move reverify walks off request path (audit8 H1 d,e)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T14:41:38Z"
updated = "2026-11-10T14:55:02Z"
scope = ["python/sadi/store/**", "python/sadi/server/curve_source.py"]

[[acceptance]]
text = "_scan_notes needs no whole-WAL walk after a snapshot rebase."
bound = false

[[acceptance]]
text = "SessionReplayCache reverify walks run off the request path."
bound = false
+++

Remaining parts (d),(e) of audit8 H1; see scratchpad audit8.md.
