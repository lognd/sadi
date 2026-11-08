+++
id = "01M6W7R0N34FPB5NP8XF4KKZCS"
title = "Hardware-verification checklist mapped to protocol.md section 10"
type = "docs"
category = "done"
outcome = "done"
priority = "high"
points = 3
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:11:46Z"
idempotency_key = "sadi-hw1"
labels = ["ws:rust", "needs-board", "model:sonnet", "creates:docs/hardware-verification.md", "creates:docs/hardware/**"]
scope = ["docs/hardware-verification.md", "docs/hardware/**", "docs/index.md", "README.md"]

[[acceptance]]
text = "One checklist row per item 1-11 of docs/protocol.md section 10 (items 9-11 marked secondary/optional): what to do on the bench, expected result, how to capture evidence (hwprobe output), and which code/doc changes follow from each outcome (e.g. unipolar scaling -> codec mode default)"
bound = true

[[acceptance]]
text = "Each row names the sadi-proto symbol or config switch that encodes the unverified assumption, and a pass/fail/blocked status column"
bound = true

[[acceptance]]
text = "Includes safety notes (LVDT supply, +-5 V limits) and session record template to commit raw captures under docs/hardware/captures/"
bound = true
+++

This ticket is the single mapping from 'needs the physical board' to code. Items: FTDI part/FIFO mode and 612 kB/s at latency 2 ms; ADS8684 vs ADS8688; unipolar scaling and bipolar extremes; encoder sign and high-word continuity; unexpected firmware output and Query/Stop interleaving; boot time after Reset; digital input pin mapping; back-to-back commands.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
