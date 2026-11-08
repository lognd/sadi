+++
id = "01M6WSQ57BQ8EZYECPGPFQFWB7"
title = "ad3: FakeDwf simulated device backend and SADI signal-injection bench"
type = "task"
category = "in-progress"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-08T05:22:23Z"
updated = "2026-11-08T05:30:51Z"
labels = ["ws:py", "ad3", "model:sonnet", "creates:python/sadi/bench/ad3/fake.py", "creates:python/sadi/bench/inject.py", "creates:python/tests/bench/test_ad3_fake.py", "creates:docs/bench/injection.md"]
scope = ["python/sadi/bench/ad3/fake.py", "python/sadi/bench/inject.py", "python/tests/bench/test_ad3_fake.py", "docs/bench/injection.md", "docs/index.md"]

[[acceptance]]
text = "FakeDwf satisfies the DwfBackend Protocol and generates and samples waveforms deterministically with no hardware"
bound = true

[[acceptance]]
text = "sadi.bench.inject drives any DwfBackend to inject signals and capture outputs, with pin mapping supplied as validated configuration"
bound = true

[[acceptance]]
text = "A loopback test through FakeDwf and the SADI simulator model runs in CI"
bound = true

[[acceptance]]
text = "Cross-platform: FakeDwf and inject behave identically on Windows, macOS and Linux (no OS-specific code paths outside sadi.bench.ad3.dll)"
bound = true
+++

In-memory FakeDwf implementing the DwfBackend Protocol (from ~SHEH6FP) with a deterministic model: analog out channels generate waveforms (dc/sine/ramp/custom), scope channels sample them with configurable gain/offset/noise, so tests run with no hardware. Plus sadi.bench.inject: helpers that drive a DwfBackend to inject LVDT-like and load-channel analog signals toward a SADI board and capture its outputs, written against the Protocol so the same test runs on real AD3 hardware later. Wiring/pin mapping is configuration (pydantic) not hard-coded; real-board mapping is unknown and left as TODO ticket for the hardware session. Compose with the existing sadi simulator where useful (loopback test: FakeDwf waveform -> expected SADI ADC counts via the simulator model). Standards: ASCII only; module logger never print; docstring on every public symbol; docs Status: header; tests in same change; Python only. typani Result/ErrorSet, pydantic. NEVER add Co-Authored-By.
