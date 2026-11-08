# LCTT creep fit

Status: current

Owner: ~7NDJSG8. Code: `python/sadi/labs/lctt/creep.py`.
Tests: `python/tests/labs/lctt/test_creep.py`.

After a load change the strain keeps creeping roughly linearly in log time. The fit
describes one hold (one load level) as `strain = a + b * ln(t - t_load)`, pure and
deterministic with no I/O. It matches the simulator's creep law
(`amp * ln(1 + dt/tau)`, see `crates/sadi-proto/src/sim/physics.rs`), whose log slope tends to `amp`
for `dt >> tau`.

## API

`fit_creep(times, strain, t_load, t_ref, config=None)` returns
`Result[CreepFit, CreepError]`. Samples must all lie after `t_load`, with strictly
increasing times.

`CreepFit`: `a` and `b` (`Measured`, dimensionless, dof n-2, OLS standard errors),
`r2`, `n_points`, `t_ref` and `strain_at_ref`, the extrapolated strain at `t_ref` as a
`Measured` whose uncertainty uses the full (a, b) covariance, so it grows with distance
from the data.

## Config and errors

`CreepConfig` (frozen): `min_points` (default 5, >= 3) and `min_decades` (default 0.5,
log10 span of `t - t_load`). A hold below either gives `CreepError.HoldTooShort`.
Other `CreepError` members: `LengthMismatch`, `NonFinite`, `NonMonotonicTime`,
`BeforeLoad`, `BadReference`, `NotRepresentable`.

## Consumers

`b` is the number the creep strain-vs-log-time plot shows per hold. A small `b` with a
tight standard error supports the settle suggestion ([settle detector](settle.md)); a
large `b` supports a forced-early decision being flagged as still creeping. The fit only
reports; a human decides.
