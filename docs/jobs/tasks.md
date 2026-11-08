# Progressive job tasks
<!-- frob:waive DOC007 docs/README.md is leased by another ticket; link filed separately -->

Status: current

Owner: ~PX6X3ZQ. Code: `python/sadi/jobs/tasks/` (`mc.py`, `gp.py`, `_drive.py`).
Tests: `python/tests/jobs/test_tasks.py`. Subject: [jobs.md](jobs.md); harness: [testing.md](testing.md).

Two CPU tasks that refine their answer while they run, so the results stream can show a
`refining` value that tightens and a `final` one. Both run on the job pool and are
superseded by a newer `data_version` on the same `JobKey` (latest wins, see jobs.md).

## Shape of a task

Each task is a generator core (`mc_steps`, `gp_steps`) plus a worker entry point
(`run_mc`, `run_gp`). The core yields a `Tick(fraction, partial)` per progress point and
receives the cancel flag; it returns `Result[dict, TaskError]`. `drive()` forwards ticks to
`CancelToken.check`, returns `{}` on cancel (the pool then reports Cancelled) and raises on
`Err` at the worker boundary (the pool turns that into a Failed event). Because cores are
plain generators, the J2 harness runs them as scripts with no processes or sleeps.

`TaskError`: `BadInputs`, `BadFunction`, `Compute`.

## Monte Carlo (`sadi.jobs.tasks.mc:run_mc`)

Inputs (`McJobInputs`): `fn` (`module:function`, vectorised over sample columns), `means`,
`cov`, `seed`, `target` (samples), optional `batch_size` (4096), `batches_per_tick` (1),
`marginals`, `dofs`. The function is an import path because callables are never pickled.

Each tick runs `batches_per_tick` more batches and publishes the cumulative estimate:
`n, mean, std, low, high, se_mean, se_std, seed, target, halfwidth_mean` with
`fraction = n / goal`, where goal is `target` rounded up to whole batches. Batch `k` always
uses stream `(seed, k)`, so the final value equals a single-shot
`McSampler.run_to(target)` with the same seed regardless of chunking. A cancel stops the run
at the next tick and discards the partial work.

## GP fit and suggestion (`sadi.jobs.tasks.gp:run_gp`)

Inputs (`GpJobInputs`): `x` (n rows of d), `y` (n), `candidates`, `noise`, `lengthscales`
(default 12 log-spaced values). A zero-mean RBF GP with signal variance `var(y)` is fitted at
each lengthscale in turn; each tick publishes the best-likelihood fit so far
(`lengthscale, signal_var, log_marginal`) and, when candidates exist, a `suggestion`
(`index, point, sd`): the candidate with the largest posterior sd. No candidates, no
suggestion. A singular lengthscale is skipped; the job fails with `Compute` only if all are.
This is a generic uncertainty-sampling GP; the project-specific selector was removed
(~2AJZS6W).

## Supersede and determinism

A new captured point means a new `data_version`: submitting it for the same key supersedes
the in-flight job, whose late partials are discarded by the manager and which never
publishes a `final`. Tests cover this under seeded `Interleaver` runs: the same seed yields
the same trace and the same final value.

## Limitations

- GP cost is O(n^3) per lengthscale; there is no mid-fit cancel inside one lengthscale.
- MC cancel latency is one tick (`batches_per_tick` batches).
