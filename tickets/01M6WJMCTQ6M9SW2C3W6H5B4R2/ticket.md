+++
id = "01M6WJMCTQ6M9SW2C3W6H5B4R2"
title = "events.replay rejects any rotated WAL: SEAL seq looks like a gap (EventsGap)"
type = "bug"
category = "in-progress"
priority = "critical"
points = 3
reporter = "lognd"
created = "2026-11-08T03:18:33Z"
updated = "2026-11-08T03:23:16Z"
scope = ["python/sadi/store/events.py", "python/tests/store/test_events.py", "python/sadi/store/wal.py", "docs/store/events.md", "docs/store/wal.md"]
+++

found while working ~HAH4MTB. replay() sets started after the first record then requires rec.seq == covers_seq+1, but SEAL records consume a seq and are not yielded by WalReader.records(), so every multi-segment WAL fails replay_wal/recover_state with EventsGap(expected=N, found=N+1) right after the first rotation. Recovery (and snapshot-assisted recovery, whose base.covers_seq precedes a seal) of any session larger than one segment is therefore impossible through events.py; WAL bytes are intact. Repro: python/tests/crash harness with segment_max_bytes=6000. Fix: tolerate seq jumps that are exactly seal seqs (or have the reader yield seals / report them) and add a rotation test.
