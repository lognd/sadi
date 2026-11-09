+++
id = "01M701SFR4E1BKBXW1RCN14TK3"
title = "ci: windows crash tests (power-loss-25 bad segment magic, stale-lock, artifact lock copy) and harness E501"
type = "bug"
category = "in-progress"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-09T11:41:11Z"
updated = "2026-11-09T11:46:20Z"
scope = ["python/sadi/store/lock.py", "python/tests/crash/harness.py", "python/tests/store/test_lock.py"]

[[acceptance]]
text = "ruff check python passes; crash tests pass on Linux and logic is sound for Windows; no invariant weakened"
bound = false
+++

CI run on main: python ruff E501 at python/tests/crash/harness.py:135 (comment >100 cols). Windows crash job: test_power_loss_truncation_recovers[25] WalSegmentHeaderInvalid segment=7 bad segment magic; test_stale_lock_is_never_broken_silently second open succeeds on Windows; test_random_kill_recovers[177] shutil.Error WinError 33 copying lock files into crash-artifacts. Investigate whether truncated segment header is a real recovery gap (fix product + regression test) or harness artefact. Do not weaken data-safety invariants. Fetch logs: gh api repos/lognd/sadi/actions/jobs/<id>/logs.
