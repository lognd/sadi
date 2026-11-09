+++
id = "01M6Z5X8ABWY83TMY0ETZBMN5W"
title = "detect_slip: production callers must set noise_floor to one ADC LSB (default 1e-12 over-triggers on quantised near-constant data); audit callers and add a derived default"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:33:55Z"
updated = "2026-11-09T03:36:25Z"
idempotency_key = "gap-slip-noise-floor"
scope = ["docs/lctt/slip.md", "python/sadi/labs/lctt/slip.py", "python/tests/e2e/test_lctt_ad3.py", "python/tests/labs/lctt/test_slip.py"]

[[acceptance]]
text = "slip_config_from_adc derives noise_floor from one ADC LSB; quantised hold gives no events, real glitch detected"
bound = true
+++
