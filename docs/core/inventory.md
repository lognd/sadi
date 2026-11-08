# Weight inventory

Status: current

Owner: ~N0YH4FG. Code: `python/sadi/core/inventory.py`.
Tests: `python/tests/core/test_inventory.py`.

## Entry and history

Weights are numbered 1, 2, 3, ... and entered once as `WeightSet` events (mass kg, mass
uncertainty, height m, height uncertainty; all SI, 1-sigma). The events are JSON payloads
(`parse_event` reads one back) meant for the WAL. An edit is a later `WeightSet` for the
same number: the latest wins, `Inventory.history(n)` returns every version. `Inventory` is
immutable; `record(event)` returns a new one or an `InputError`.

## Group balance weighing (Q7)

`GroupWeighed(name, numbers, mass, u_mass)` records a named subset weighed together.
`reconcile()` treats the group reading as an independent measurement of the sum of its
members and merges it with the individual masses by generalised least squares:
`K = V A^T (A V A^T + R)^-1`, `m' = m + K (g - A m)`, `V' = V - K A V`. The posterior masses
are therefore correlated (a precise group reading anti-correlates its members). A group whose
reading differs from the individual sum by more than 2 combined sigma yields a
`ConsistencyWarning`. Exact redundant readings (zero uncertainty everywhere) are a
`ComputeCode.DEGENERATE` error.

## combo(weight_ids)

`Inventory.combo(ids)` returns `Combo(mass, height, source, choices, warnings)`:

- height is the stack sum of heights with independent uncertainties;
- mass candidates are `individual` (sum of individual masses), `group` (only when the ids are
  exactly a weighed group) and `combined` (reconciled, full covariance). The one with the
  lowest uncertainty is used; `choices` lists all of them so the UI can show the choice.
  Sums are propagated with `sadi.uncertainty` (`Measured`, `CovarianceRegistry`).

`to_weight_inventory()` exports reconciled masses as the core `WeightInventory`.
