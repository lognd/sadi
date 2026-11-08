+++
id = "01M6WSPW5XB6P5V3PR5SHEH6FP"
title = "ad3: typed Digilent DWF binding (ctypes edge, Protocol backend, Result errors)"
type = "task"
category = "in-progress"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-08T05:22:14Z"
updated = "2026-11-08T05:26:36Z"
labels = ["ws:py", "ad3", "model:sonnet", "creates:python/sadi/bench/__init__.py", "creates:python/sadi/bench/ad3/__init__.py", "creates:python/sadi/bench/ad3/consts.py", "creates:python/sadi/bench/ad3/backend.py", "creates:python/sadi/bench/ad3/dll.py", "creates:python/tests/bench/test_ad3_binding.py", "creates:docs/bench/ad3.md"]
scope = ["python/sadi/bench/**", "python/tests/bench/**", "docs/bench/ad3.md", "docs/index.md"]

[[acceptance]]
text = "Loading with no libdwf present returns a typed Err with a step-by-step fix hint; import of sadi.bench.ad3 never fails"
bound = true

[[acceptance]]
text = "Backend calls marshal arguments and out-params correctly and map nonzero DWF status to Err carrying the last error message (verified with an injected fake library)"
bound = true

[[acceptance]]
text = "Device handle is move-only (typestate): using a closed handle is a type error and a runtime Err"
bound = false
+++

Library to operate a Digilent Analog Discovery 3 programmatically so SADI can be tested end to end. Package sadi.bench.ad3. Constants/enums transcribed from the WaveForms SDK header (read-only reference: /mnt/c/Program Files (x86)/Digilent/WaveFormsSDK/inc/dwf.h; do not vendor the header or DLL). DwfBackend Protocol covering the subset needed: enumerate/open/close, analog out (FDwfAnalogOut*: node/function/frequency/amplitude/offset/configure), analog in scope (FDwfAnalogIn*: channel enable/range/frequency/buffer/configure/status/get data), analog IO (supplies), digital IO basics. Real backend: ctypes over libdwf (Linux libdwf.so, Windows dwf.dll, macOS dwf.framework) loaded lazily; library-missing and device-missing are typed Err (ErrorSet), never import-time failures. Typestate handles: Closed -> Open device consumed by close. Hardware is NOT available: tests must use a fake ctypes library object injected into dll.py to verify argument marshalling and error mapping (FDwfGetLastErrorMsg). Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; docs page with Status: header linked from docs/index.md; tests in the same change; stay in scope. Python only (no cargo): typani Result[T, E] with ErrorSet error families (isinstance(x, Ok) + unwrap_err idiom), pydantic, no unsafe tricks beyond ctypes at one edge module; run ruff, ty, python -m typani.lint. NEVER add Co-Authored-By.
Acceptance
1. Loading with no libdwf present returns a typed Err with a step-by-step fix hint; import of sadi.bench.ad3 never fails
2. Backend calls marshal arguments/out-params correctly and map nonzero DWF status to Err carrying the last error message (verified with an injected fake library)
3. Device handle is move-only (typestate): using a closed handle is a type error and a runtime Err
