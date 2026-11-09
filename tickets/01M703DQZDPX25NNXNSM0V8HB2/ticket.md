+++
id = "01M703DQZDPX25NNXNSM0V8HB2"
title = "ci: windows browser e2e guided-run fails (durability timeouts on windows)"
type = "bug"
category = "in-progress"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-09T12:09:44Z"
updated = "2026-11-09T12:13:17Z"
scope = ["web/e2e/**"]

[[acceptance]]
text = "e2e guided run robust on windows; durability never weakened; ubuntu/macos e2e unaffected"
bound = true
+++

CI run 42611896010 E2E windows: e2e/guided-run.spec.ts keyboard-only guided run fails after 25.8s; server logs show many 'wait_durable(N) timed out after 0.2s' and 'clamp status: 0/3 cycles passed=None'. Determine whether the 0.2s durability wait is too tight for Windows fsync (config/timeouts in e2e server startup or product default) or a real bug; get full log: gh api repos/lognd/sadi/actions/jobs/129142126971/logs. Do not weaken durability: a longer wait/timeouts for tests is fine, dropping fsync is not.
