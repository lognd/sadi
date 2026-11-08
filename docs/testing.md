# Backend end-to-end testing: simulator fault injection

Status: current

Parent: [concurrency-testing.md](concurrency-testing.md), [data-safety.md](data-safety.md).
Ticket: ~WKK27QJ. Code: `python/tests/e2e/`.

The suite drives the Rust device simulator (`sadi_py.sim`) through the real
`AcquisitionPipeline` into a real WAL, then asserts on settle behaviour, slip
and saturation detection, resync accounting, ground-truth agreement and raw
preservation. It skips when the native extension is not built.

## Scenario matrix

All scenarios run 0.6 s of simulated time with a 1 kg load change at 0.1 s,
with noise and creep explicitly zeroed unless the scenario injects them.

| Scenario   | Injected fault                                   | Asserted                                                   |
|------------|--------------------------------------------------|------------------------------------------------------------|
| noise      | white noise, sd 2 mV                             | pre-load sd matches the plan; point SETTLED                |
| drift      | 3 V/s linear drift                               | never settles (CREEPING); measured rate matches            |
| creep      | log creep, coeff 0.5, tau 10 ms                  | SETTLED with a positive sub-threshold drift rate; log slope matches ground truth |
| slip       | 0.005 strain step at 0.4 s                       | `slip_count` 1; `detect_slip` reports one event at 0.4 s   |
| dropped    | 100 and 37 bytes cut from two blocks             | two `RAW_JUNK` records; dropped and gap counts add up; analysis continues |
| saturation | clamp at 1.005 V                                 | `check_saturation` flags "may be clipping"; peak at clamp  |
| combined   | noise, creep, slip, clamp 1.1 V, one dropped gap | each fault still surfaces                                  |

Every scenario (plus the fault-free baseline) also runs
`test_raw_is_preserved_in_the_wal`: each ingested byte is in the WAL, in order,
as `RAW_BLOCK` or, after a gap, `RAW_JUNK`.

## Kill during a run

`test_kill_resume.py` starts `killee.py`, which creates a real session and
ingests simulator batches. After the first batches are durable the test sends
SIGKILL, scans the WAL, calls `resume_session` (recovering the stale data-root
lock), and continues the run in the new version `v002`. It asserts that `v002`
links to `v001` (`parent`, `parent_last_seq`) and that `v001` is byte-identical
before and after the resume.

## How to add a scenario

1. Add a `Spec` to `python/tests/e2e/scenarios.py` (fault dict in the
   simulator scenario schema; `drops=` for byte loss) and append it to `MATRIX`.
2. Add a test in `test_fault_scenarios.py` that calls `_run(SPEC, tmp_path)`
   and asserts on the `Run` (statuses, results, records, `slip_count`, ...).
   Tag it `# frob:tests` with the code it covers. The parametrised raw
   preservation test picks the new spec up automatically.
3. Bind the new node as ticket evidence.

## Design notes

- Analysis is decimated by 25 (50 kHz to 2 kHz) and sent in 10-block batches:
  the streaming settle detector used to re-fit the open point on every push;
  it now scans incrementally (O(1) amortized per sample, see `SettleScanner`),
  so the decimation is no longer required for speed. The raw bytes are never decimated.
- `ByteFaultPlan` is exposed as `sadi_py.sim.open(..., byte_faults=...)` (see
  `docs/device/python-binding.md`), but the dropped scenarios still emulate
  loss test-side: a real plan corrupts the stream per byte, so the framer
  resynchronises and the lost-byte count is not controllable per block. The
  harness cuts exact byte counts from the batch raw and sets `dropped_bytes`
  and `gap_events`, which is what the framer reports to ingest, so the
  assertions stay exact. Use `byte_faults` for statistical or robustness tests.
- Simulator defaults inject noise and creep when a plan omits them, so
  scenarios set explicit zeros (`QUIET`) to keep faults separable.
