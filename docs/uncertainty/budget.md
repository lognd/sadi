# Uncertainty budget

Status: current

`Uncertain.budget(*measured)` (python/sadi/uncertainty/budget.py) returns
`Result[Budget, UncertainError | UncertaintyError]`: the per-input breakdown of the result
variance for an [@uncertain](uncertain.md) function.

## Rows

Each `BudgetRow` (frozen pydantic model) holds `name`, `id`, `value`, `unit`, `std_unc`, the
sensitivity coefficient `c_i = df/dx_i`, and:

- `direct = c_i^2 u_i^2`
- `cross = c_i * sum_{j != i} c_j cov(x_i, x_j)` (covariance terms attributed to row i)
- `contribution = direct + cross`
- `percent = 100 * contribution / total_variance` (0 when the total is 0)
- `rank` (1 = largest absolute contribution)

Each pair cross term `2 c_i c_j cov_ij` is split evenly between rows i and j, so the
contributions sum to `J C J^T` (the full-covariance variance) for correlated inputs. With
negative correlation a contribution or percent can be negative.

## Payload

`Budget.rows` is ranked; `Budget.dominant` is the rank-1 row; `Budget.payload()` is a
JSON-safe dict (`total_variance`, `total_std_unc`, `dominant`, `rows`) for the UI
dominant-input panel.

## Guarantee

`sum(contribution) == total_variance` (math.fsum), equal to the `std_unc**2` of calling the
function on the same inputs; property-tested with random correlations.

See also: [weight-plan error propagation](weight-plan.md).
