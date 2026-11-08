# frob parse holes on `match` statements

Status: current

Owner: ~Z09R6VM. Affects: `python/sadi/core/device.py`,
`python/sadi/jobs/{manager,pool,state,testing}.py`,
`python/tests/store/test_lock.py`, `tools/check_typani_collisions.py`.

## Finding

`frob check` reports "the file parsed partially (N hole(s))" (DOC001,
COV001, AFFECT001 undecided) for exactly the seven files that contain a
Python `match` statement. The hole count equals the number of `match`
statements in each file (state.py 3, testing.py 3, test_lock.py 3,
manager.py 2, device.py 1, pool.py 1, check_typani_collisions.py 1).
A minimal probe file holding a single `match x: case 1: ...` produced one
hole; the same file without the `match` produced none. Walrus, lambdas,
`await` and f-strings do not trigger holes. The cause is frob's bundled
tree-sitter Python grammar, which does not parse structural pattern
matching.

## Decision

The code is left unchanged. Rewriting the `match` statements as `if` /
`isinstance` chains would drop the `assert_never` exhaustiveness checks
that `ty` enforces over enums and `Result` (`Ok` / `Err`) values, and
would diverge from the typani idiom used across the repo. The limitation
is recorded here instead.

## Consequences

- Public symbols in those files are unseen by frob; DOC001 and COV001
  are undecided for them, not failed. Keep docstrings and `frob:tests`
  markers on them anyway.
- The note disappears once frob's grammar handles `match`; no code
  change will be needed.
