+++
id = "01M703DQWZ3TFQ5FXAKVYZ1DZT"
title = "ci: windows crash tests - lock released lazily after kill, manifest.json PermissionError"
type = "bug"
category = "done"
outcome = "done"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-09T12:09:44Z"
updated = "2026-11-09T12:13:30Z"
scope = ["python/tests/crash/**"]

[[acceptance]]
text = "bounded-retry for lock release and manifest read in harness (or product if real bug); Linux crash suite still passes; no invariant weakened"
bound = true
+++

CI run 42611895944 crash (windows): test_random_kill_recovers[94,121,186] fail 'resume failed even with recover_stale: LockHeld pid None' (killed process byte-range locks released lazily; resume must retry/poll briefly for lock release in the harness, never break a live lock silently); [32,46] PermissionError reading sessions/*/manifest.json (file still held/replaced by killed writer or antivirus; harness read must retry with bounded backoff). Logs: gh api repos/lognd/sadi/actions/jobs/129142126642/logs. Prior fix ~CN14TK3 already landed (see git log). Do not weaken invariants; product bug => fix + regression test.
