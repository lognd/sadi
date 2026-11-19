# Weight plan

Status: current

Owner: ~YNKT2ED.

Advisory planner that chooses which of the (up to 12, normally 8) inventory weights to hang, in order,
with the uncertainty of each hang (front ends: [planner-gui.md](planner-gui.md)). Code: `sadi/design/plan.py`; payloads: `sadi/design/models.py`
(`Weight`, `PlanRequest`, `Hang`, `WeightPlan`). It never writes data.

## Method

1. Enumerate the 2^n - 1 non-empty subset sums (more than 120 weights is a `TooManyWeights` error).
   Duplicate weights are distinct ids. Subsets with equal total mass collapse to one load that keeps
   the lowest ids, so the plan is deterministic.
2. Drop loads whose predicted |V| exceeds the saturation threshold (`DEFAULT_SATURATION_V`, or the
   request override) or whose tension exceeds `capacity_fraction` (1.0) of the wire's break load
   (`break_stress_pa` = 250 MPa; a real wire broke just above 8 N at 0.2019 mm). Capacity is
   advisory: a user-set max weight overrides it, and if it would drop every load the planner
   plans anyway and returns a `warnings` entry. It never blocks a plan.
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
   In the yield phase the half-width is of the yield load (N).

## Replanning

Pass `captured` points (mass, volts, uncertainty). They seed the selector and set a floor: only
heavier loads are planned.

## Errors

`PlanError`: `NoWeights`, `TooManyWeights`, `DuplicateIds`, `NonFinite`, `NoUsableHang`,
`SelectorFailed`.

Note: a 32 AWG copper wire breaks near 4.2 N, so heavy inventory weights are dropped
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
hang with total mass, tension, predicted volts and the planner's reason. After a plan, "Save weights
to this session" appends the entered inputs as an inventory event (see below).

## Persistence and replanning

- `POST /api/weight-plan/inventory` appends the entered inventory (weights, wire geometry, optional
  slope) as a JSON NOTE record tagged `weight_plan_inventory` in the session WAL, durable before the
  response. Nothing is overwritten or deleted: an edit is a later event, the latest wins, and the
  earlier versions stay in the WAL (and are copied into resumed sessions like all NOTEs). Saving
  inputs identical to the latest event writes nothing. With no open session the answer is 409.
- `GET /api/weight-plan/inventory` returns the latest saved inputs and the event count.
- `GET /api/weight-plan/next` replans from the latest saved inventory and the session's settled
  elastic points (`PlanRequest.captured`), returning `{captured, next_hang, reply}`; 404 when nothing
  is saved. Advisory and read-only. The Run screen's `NextHangPanel` (elastic step) shows `next_hang`
  and refetches after each captured point.
- These events are kept separate from plugin `InventoryProvider` events (docs/server/inventory.md),
  so they can never corrupt a plugin's inventory fold.
