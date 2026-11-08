# Simulator physics and signal faults
Status: draft

`sadi_proto::sim` is the test oracle for settle, creep and slip logic
(real data is unavailable; the local short run is slip-contaminated and is
only a slip-detector case). Gauge length L0 is set in the scenario.

## Modules
- `sim::physics`: wire, load program, LVDT. Strain is the sum of elastic
  `sigma/E`, plastic hardening `(sigma_peak - sigma_y)/H` (permanent, set
  by the peak stress so far), log-time creep and slip jumps. Creep uses
  superposition: each load change adds
  `coeff * (d sigma / E) * ln(1 + dt/tau)`, so the strain-vs-ln(t) slope
  of a hold is `coeff * d sigma / E`. LVDT: `V = sign * (L - offset) / slope`;
  default slope 2.114583e-3 m/V, default offset puts the unloaded wire at 1 V.
- `sim::signal_faults`: serde `FaultPlan`: noise (white, or coloured as a
  moving average rescaled to keep the sd; default sd 0.0345 V), linear and
  thermal drift, creep law, slip steps (timestamp + strain, no load
  change), saturation beyond |V| > 4.9 either `clamp` or `fold` (triangle
  reflection, so voltages repeat). Drift and saturation act on channel 0
  (LVDT) only; other channels carry noise only.
- `sim::scenario`: `Scenario` (wire, lvdt, load, faults) implements
  `SignalSource`. `Scenario::builtin(name)` loads the shipped JSON in
  `crates/sadi-proto/scenarios/`: clean, noisy, drifting, creeping,
  slipping, saturating, combined. Downstream tests should use these.

## Determinism
Noise is a pure function of (seed, channel, sample index at
`sample_rate_hz`), so `voltage(&self, ch, t)` needs no state and the same
seed always yields the same samples. No RNG crate is used.

## Type-level design choices
- Newtypes `Positive` and `NonNegative` (private field, validating
  constructor, serde `try_from`) make bad diameters, moduli, slopes,
  rates, tau, limits and noise sd unrepresentable; JSON with such values
  fails to parse. `Seed` wraps the noise seed.
- `FaultKind` enumerates the fault types; `FaultKind::is_active` is an
  exhaustive match with no wildcard. Fault and error enums are
  `#[non_exhaustive]`; `Polarity` and `SaturationMode` are enums rather
  than integer codes.
- Plans and scenarios are parsed once into typed values
  (`Scenario::from_json`, `deny_unknown_fields`); only load-step ordering
  is checked at runtime (`ScenarioError::Invalid`). Builder methods
  (`with_seed`, `with_noise`, `with_drift`, `with_saturation`,
  `with_faults`) consume `self`; pure accessors are `#[must_use]`.

## Tests
`crates/sadi-proto/tests/sim_physics.rs` recovers E, plastic strain, drift
slope, noise sd, creep slope (exact without noise, 15% through noise) and
slip sizes (10%) from sampled output, and checks determinism and
saturation.
