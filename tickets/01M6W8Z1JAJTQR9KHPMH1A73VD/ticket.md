+++
id = "01M6W8Z1JAJTQR9KHPMH1A73VD"
title = "Settle detector streaming layer: states, load-change markers, per-point record, fixed-dwell, simulator tests"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-08T00:29:36Z"
updated = "2026-11-08T00:37:31Z"
labels = ["ws:py", "lctt", "creates:python/tests/labs/lctt/test_settle_stream.py", "creates:python/sadi/labs/lctt/settle_stream.py"]
scope = ["python/tests/labs/lctt/test_settle_stream.py", "python/sadi/labs/lctt/settle_stream.py", "docs/lctt/settle.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1KH0MVS56MX07Q9BX19"

[[acceptance]]
text = "Streaming detector over raw LVDT blocks emits loading/creeping/settled with drift rate and time since load change"
bound = true

[[acceptance]]
text = "Load-change detection from marker events; raw is always recorded regardless of state"
bound = true

[[acceptance]]
text = "Each point stores window, time-since-load, drift rate and settled/forced-early flag; fixed-dwell mode is a config option"
bound = true

[[acceptance]]
text = "Tested on simulator scenarios clean/noisy/creeping/drifting: no false settle under noise, settles within expected dwell"
bound = true
+++

Split from ~7Q9BX19, which delivered the pure windowed detector (settle.py). Builds the streaming and per-point layer on top.
