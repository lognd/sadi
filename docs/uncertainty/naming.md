# Uncertainty: typani name-collision check

Status: current

`sadi.uncertainty` must never define or re-export a name that typani exports
(`propagate`, `catching`, `Result`, `Ok`, `Err`, `ErrorSet`, `UnwrapError`, ...). That is why the
decorator is called `uncertain` (see [@uncertain](uncertain.md)).

## The check

`tools/check_typani_collisions.py` introspects `typani.__all__` (dunders excluded) at run time, so
new typani exports are covered automatically. It fails (exit 1, problems on stdout) when:

1. `sadi.uncertainty.__all__` contains any typani public name, or
2. any `python/**/*.py` line matches `import ... as <typani name>` aliasing.

Run: `uv run --project python python tools/check_typani_collisions.py`

## Tests and CI

`python/tests/test_typani_collisions.py` runs the same checks under pytest, plus asserts
`from typani import propagate` and `from sadi.uncertainty import uncertain` coexist. The CI lint
step runs the script when the file exists.
