+++
id = "01M6Z3FR114SYB4SDYQVQPGZXY"
title = "AD3 LCTT source: replace stand-in raw framing with the real SADI protocol framer"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-09T02:51:35Z"
updated = "2026-11-09T02:57:52Z"
scope = ["python/sadi/bench/lctt_source.py", "docs/bench/lctt-ad3-matrix.md", "python/tests/e2e/test_lctt_framing.py", "changelog.d/01M6Z3FR114SYB4SDYQVQPGZXY.changed.md"]

[[acceptance]]
text = "Given an AD3 volts block, when to_block runs, then raw is whole 612-byte SADI type-5 packets with sync, LE msg_count, BE codes and tail"
bound = true
+++

found while working GHQ8PEY
