# LCTT test flow driven by the AD3

Status: current

Parent: [ad3.md](ad3.md), [injection.md](injection.md)

Verification: CI runs every stage below against `FakeDwf` plus a modelled SADI ADC
(`python/tests/e2e/test_lctt_ad3.py`). The `ad3_hw` tests
(`python/tests/bench/test_lctt_ad3_hw.py`) have NOT been run: the AD3 is detached from
WSL and needs an admin `usbipd` bind. They auto-skip unless libdwf loads, an AD3
enumerates and `SADI_PORT` is set.

The AD3 produces every test voltage through `sadi.bench.lctt_source.Ad3Source`
(`inject_dc` / `inject_lvdt`), the ADC model quantises it, the result is packed into
raw blocks and fed to the real `AcquisitionPipeline`, WAL and LCTT analysis. All
levels stay at or below 1 V (`MAX_SAFE_V`).

| Stage | AD3 stimulus | Expected result | Status |
|---|---|---|---|
| Calibration | 5 DC levels 0..0.8 V on the LVDT route, no load | slope 0.01 m/V, r2 > 0.9999 | CI |
| Zero / tare | 0.2 V held | tare 0.2 V | CI |
| Saturation / clamp check | 0.9 V vs 0.5 V levels, threshold 0.8 V | flag set only for 0.9 V | CI |
| Load ramp | staircase of 8 LVDT/load steps, strain swing about 14 mV | E within 1 percent of 70 GPa, r2 > 0.999 | CI |
| Settle / hold | flat dwell after each step | every point SETTLED, none forced early | CI |
| Creep | rising 0.2..0.7 V staircase | state stays CREEPING | CI |
| Modulus + uncertainty | ramp above | E and slope carry a finite std uncertainty < 5 percent | CI (no Monte Carlo) |
| Slip detection | 4 mV step mid-hold | one event near the step; clean hold none | CI |
| Capture record | all blocks | every block byte-identical in WAL, in order, no junk | CI |
| Export CSV | exported twice | atomic, numbered, never overwrites, E round-trips | CI |
| Crash / resume | SIGKILL mid-acquisition | v001 digest unchanged, v002 completes full flow | CI |
| Live stream | bus subscription | LOADING first, SETTLED last, one result per point | CI |
| Unload | return to tare, zero load | extra settled point | CI |
| LVDT sine | `inject_lvdt` 0.5 V, 1 kHz | amplitude read back within 1 percent | CI |
| Yield stress | n/a | stays pending (elastic-only run) | follow-up |
| Hardware loopback | DC levels, staircase | see `ad3_hw` tests | not run |

## Known gaps

- The raw framing in `Ad3Source.to_block` is a stand-in, not the real SADI protocol.
- The fake supports only SINGLE acquisition, so there is no true continuous streaming.
- On real hardware scope ch0 monitors the supply, so the LVDT read-back must come from
  the SADI board via the serial facade, which does not exist yet.
