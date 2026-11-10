# Weight plan

Status: current

Owner: ~YNKT2ED.

Advisory planner that chooses which of the (up to 12, normally 8) inventory weights to hang, in order,
with the uncertainty of each hang (front ends: [planner-gui.md](planner-gui.md)). Code: `sadi/design/plan.py`; payloads: `sadi/design/models.py`
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

## Route and UI

`POST /api/weight-plan` (python/sadi/server/routes/weight_plan.py) takes weights (mass, optional
uncertainty), wire diameter and L0 with uncertainties, and an optional LVDT calibration slope
(V per m). It is stateless and needs no lab or open session. When the slope is omitted it is fitted
from the current session's LVDT calibration points; with neither, the route answers 422 with a hint.
`GET /api/weight-plan/defaults` reports that default and where it comes from. The reply carries the
ordered hangs and the uncertainty from `sadi.labs.lctt.propagate` (stress per hang, E, yield) for
the elastic plan. Planner refusals (`PlanError`) are 422 problems.

The "Weight plan" button in the app header opens `WeightPlanPanel` (web/src/screens/setup), which
accepts weights one per line (g or kg), keeps the form in the browser's localStorage, and shows each
hang with total mass, tension, predicted volts and the planner's reason. It is not yet wired into the
Run screen's replanning and does not write inventory events.
