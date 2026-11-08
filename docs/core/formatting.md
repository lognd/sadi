# Result formatting

Status: current

Owner: ~M27Y4NY. Code: `python/sadi/core/formatting.py`.
Tests: `python/tests/core/test_formatting.py`.

Implements the class rule (docs/domain.md): results to 3 significant figures,
uncertainties to 2. Counts live in `FormatConfig` (`result_sf`, `uncertainty_sf`,
`notation`) because the rubric (open question Q13) may change them.

## API (all fallible calls return typani `Result`)

- `format_result(value, u, unit="1", config)` -> `'v +/- U unit'`.
- `format_quantity(q, config)` for a `Quantity`.
- `plain_language_confidence(value, u95, target, label="E", config)` ->
  e.g. `E is known to within 4.2 % at 95 % confidence; target 5 % reached`.
  `target` is a fraction (0.05). "Reached" compares the displayed (rounded)
  percentage with the target. `value == 0` is `ComputeError(DEGENERATE)`.
- Errors: NaN/inf -> `ComputeError(NOT_FINITE)`; negative U -> `InputError(OUT_OF_RANGE)`.

## Rounding rules

- Round half-up on the printed (shortest-repr) decimal, not the binary float.
- Value: 3 s.f. U: 2 s.f. even when its leading digit is 1 (0.14 stays 0.14, not 0.1).
  The two are not forced to share a decimal place.
- Carry: rounding that adds a digit keeps the s.f. count (U 0.0996 -> 0.10;
  value 999.6 -> 1.00 k). The scale is chosen after rounding.
- Value and U share one scale (that of the value; of U if the value is 0), so
  U may exceed the value: `0.5 +/- 2.0 m` -> `500 +/- 2000 mm`.
- Exactly 0 prints as `0` (no significant figures to keep). `-0.0` prints as `0`.

## Notation

- `engineering` (default): exponent a multiple of 3, shown as an SI prefix
  (y..Y, micro is `u`). `kg` is shown as `g` plus prefix. Units that cannot take
  a prefix (`m^2`, `1/s`, dimensionless) use `(v +/- U)e+3` outside the unscaled
  range 1e-3 <= |x| < 1e6.
- `scientific`: one leading digit, shared exponent, no prefix, unit unchanged:
  `(1.23 +/- 0.045)e-3 m`.
