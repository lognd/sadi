# Uncertainty core: Measured

Status: current

Package `sadi.uncertainty` (python/sadi/uncertainty/). The decorator is `uncertain`
(see [@uncertain](uncertain.md)); nothing here is named `propagate` or `catching` because typani exports those.

## Measured

Frozen pydantic model: `id`, `value`, `std_unc` (standard uncertainty), `unit`, `dof`
(None = exact / Type B), `provenance`. Values are always stored in SI base units.
Build one with `Measured.create(value, std_unc, unit, dof=..., provenance=...)`, which
converts from any pint unit (offset units such as degC convert the value as a point and the
uncertainty as a difference) and registers its variance. `to_json` / `Measured.from_json`
round-trip every field; covariances live in the registry and are not serialised.

## Arithmetic

`+ - * /`, `**` and unary `-` (and the named `add sub mul div power neg`) return
`Result[Measured, UncertaintyError]`; chain with `.and_then`. Plain floats are exact
dimensionless constants. Add/sub need matching dimensions (`DimensionMismatch` otherwise).
Results use first-order propagation with the full covariance:
`var = sum_ij c_i c_j cov(x_i, x_j)`, so `x - x` is exactly 0 and `(x + y) - y` recovers `x`.

## Covariance registry

`CovarianceRegistry` (default `DEFAULT_REGISTRY`) maps ids to variances and pairwise
covariances. `Measured.correlate(other, rho)` declares a correlation. Derived quantities
inherit their covariance with every registered quantity, so correlation is not lost
through intermediate results.

## Coverage

`t95(dof)`, `interval95(value, u, dof)`, `relative_uncertainty(value, u)` and
`effective_dof([(abs(c_i) * u_i, dof_i), ...])` (Welch-Satterthwaite).

## Errors

`UncertaintyError` is a typani `ErrorSet`; each member's description is a what-to-do hint
(`hint(err)`). No fallible user-facing path raises.
