# Weight plan

Advisory planner that chooses which of the (up to 12, normally 8) inventory weights to hang, in order,
with the uncertainty of each hang. Code: `sadi/design/plan.py`; payloads: `sadi/design/models.py`
(`Weight`, `PlanRequest`, `Hang`, `WeightPlan`). It never writes data.

## Method

1. Enumerate the 2^n - 1 non-empty subset sums (more than 12 weights is a `TooManyWeights` error).
   Duplicate weights are distinct ids. Subsets with equal total mass collapse to one load that keeps
   the lowest ids, so the plan is deterministic.
2. Drop loads whose predicted |V| exceeds the saturation threshold (`DEFAULT_SATURATION_V`, or the
   request override) or whose tension exceeds `capacity_fraction` (0.95) of the wire's ultimate load.
   The material prior is `CopperSpec` (modulus, onset, ultimate); nothing is duplicated.
3. Predicted volts: `offset + cal_slope * F * L0 / (A * E_prior)` in the elastic phase; the copper
   curve (`CopperSpec.strain`) in the yield phase. The yield phase is used when at least `n_min_yield`
   points were captured and the captured stress has reached the plastic onset.
4. Order the hangs greedily with `select_next` (the GP selector, see `gp-selector.md`): each pick is
   appended as a simulated point at its predicted volts and the next pick is made from heavier loads.
   Planning stops when the selector reports enough data or no heavier load is left.
5. Each `Hang` reports weight ids, total mass, quadrature-summed mass uncertainty
   (`sqrt(sum u_i^2)`), tension, predicted volts and its uncertainty, the expected gain, and the
   slope half-width after it. The modulus half-width adds the geometry in quadrature (coverage k=2,
   diameter counted twice because A ~ d^2): `E * sqrt(rel_slope^2 + (4 u_d/d)^2 + (2 u_L0/L0)^2)`.
   In the yield phase the half-width is of the yield load (kg).

## Replanning

Pass `captured` points (mass, volts, uncertainty). They seed the selector and set a floor: only
heavier loads are planned.

## Errors

`PlanError`: `NoWeights`, `TooManyWeights`, `DuplicateIds`, `NonFinite`, `NoUsableHang`,
`SelectorFailed`.

Note: a 32 AWG copper wire breaks near 4.2 N (about 0.43 kg), so heavy inventory weights are dropped
by the capacity rule.
