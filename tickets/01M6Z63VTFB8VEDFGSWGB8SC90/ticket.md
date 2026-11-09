+++
id = "01M6Z63VTFB8VEDFGSWGB8SC90"
title = "Switch test_fault_scenarios.py and test_real_data.py detect_slip calls to slip_config_from_adc (default noise_floor is fragile on quantised data)"
type = "task"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-09T03:37:31Z"
updated = "2026-11-09T03:39:44Z"
idempotency_key = "gap-slip-callers-tests"
scope = ["python/tests/e2e/test_fault_scenarios.py", "python/tests/labs/lctt/test_real_data.py"]

[[acceptance]]
text = "Quantised e2e slip detection uses an ADC-LSB noise floor; real-data tests document why the default stays"
bound = true
+++
