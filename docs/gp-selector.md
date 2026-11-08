# GP / sequential-design selector: information gain and stop rule

Status: current

Purpose: define how SADI recommends the next weight (height) to load and when
the estimate is good enough to stop. Owner ticket: GP1 ~K80WDK8 (design).
Implementation: GP2 ~93ZD322. Candidate set: WS1 ~S5YPBEJ. Live-view
placement: ~KR3SSE1. The selector is ADVISORY ONLY: the user always makes the
stop call and the load call; nothing here acts on the machine.

Related: [uncertainty core](uncertainty/measured.md),
[settle detector](lctt/settle.md), [concurrency model](concurrency.md)
(the selector is a cancellable background job, latest wins).

## 1. Sequential design formulation

Common frame. State after n accepted observations is `D_n = {(x_i, y_i, u_i)}`
where `x` is the design variable (load step or LVDT position), `y` the settled
reading, `u_i` its standard uncertainty (a `Measured`, SI units). The model is
`y = f(x; theta) + e`, `e ~ N(0, u_i^2)`. We keep a Gaussian posterior
`theta | D_n ~ N(m_n, S_n)` and a scalar target quantity `q = g(theta)` with
linearised variance `v_n = grad_g' S_n grad_g`. The reported interval is
`h_n = t95(dof_n) * sqrt(v_n)` (half-width, from `sadi.uncertainty.t95`).

Acquisition for candidate `c` (the expected reduction in target CI half-width):

    A(c) = h_n - E[h_{n+1} | c]
    S_{n+1}(c) = (S_n^-1 + phi(c) phi(c)' / s2(c))^-1       (rank-one update)
    v_{n+1}(c) = grad_g' S_{n+1}(c) grad_g
    E[h_{n+1}|c] ~= t95(dof_n + 1) * sqrt(v_{n+1}(c))

`s2(c)` is the predicted observation variance (noise floor plus settle
residual, see section 4). The update is closed form and independent of the
unseen y for linear models, so no sampling is needed. The recommendation is
`argmax_c A(c)`; ties broken by smallest candidate index (determinism, sec 6).
D-optimal (`log det S`) and A-optimal (`tr S`) are selectable via `criterion`;
the default is target-driven (`A` above), which equals c-optimal design.

### 1.1 LVDT calibration phase

Model: `V = a + b*d` (voltage vs. known displacement), `theta = (a, b)`,
`phi(d) = (1, d)`. Target `q` = slope `b` (and, secondary, the inverse
mapping at the operating range, `g = (V - a)/b`). Candidates: gauge positions
from the WS1 set. The posterior is Bayesian linear regression with prior
`N(0, 1e6 I)` (weak), so with enough points it equals OLS. Expected behaviour:
selects the extremes first (maximal leverage), then fills the middle only if
curvature is detected (sec 4.3).

### 1.2 Elastic fit phase

Model: `delta = delta0 + k*F` (or strain-stress), `theta = (delta0, k)`,
`phi(F) = (1, F)`; target `q = E` through the specimen geometry, so
`grad_g` includes `dE/dk` and the geometry uncertainties as fixed variance
terms added to `v_n` (covariance via the registry). Candidates: WS1 weight
combinations (masses with their mass uncertainty, which enters `s2(c)` as
`k^2 u_F^2`). Only the elastic range is used (see 4.2).

### 1.3 Plastic / yield phase

Response is non-linear, so use a GP on `y = f(x)` with kernel
`k(x,x') = s_f^2 * Matern52(|x-x'|/l) + s_n^2 * delta` and hyperparameters
`(s_f, l)` fit by marginal likelihood, refit every accepted point, bounded
to a log-range prior. Target `q` = yield load (0.2% offset intersection of the
GP mean with the offset line). Posterior variance of `q` comes from
propagating GP posterior covariance at the crossing point through the
implicit-function derivative: `v = Var f(x*) / (f'(x*) - E_off)^2`. Same
acquisition `A(c)`, evaluated with the GP rank-one update
`sigma_{n+1}^2(x*) = sigma_n^2(x*) - k_n(x*,c)^2 / (sigma_n^2(c) + s2(c))`.
Candidates are restricted to a window around the current `x*` estimate
(+- 3 posterior sigma and the next WS1 steps), which also bounds cost.

## 2. Stop-early recommendation

Inputs: user target half-width `H*` (same unit as `q`, or relative), and
parameters `patience` (default 2) and `margin` (default 0.9).

    ok_n = (h_n <= margin * H*)
    stop recommended at n  iff  ok_k for the last `patience` consecutive
                                 observations k = n-patience+1..n,
                                 and n >= n_min (cold-start floor, sec 4.4),
                                 and the latest point is settled (sec 4.1)

The patience rule prevents a single lucky point from triggering. A second
reason is also reported: `diminishing` when `A(c*) < eps * h_n` (eps default
0.02) for `patience` consecutive steps, meaning more data will not help even
though the target is unmet. Neither reason ever stops anything; the UI only
shows the indicator.

### 2.1 "Confidence is enough" payload (JSON, pydantic `ConfidenceIndicator`)

    {
      "schema": 1,
      "phase": "lvdt_cal" | "elastic" | "yield",
      "job_version": int,            // concurrency.md latest-wins counter
      "n": int,
      "target": {"half_width": float, "unit": str, "relative": bool},
      "current": {"half_width": float, "value": float, "dof": float},
      "ratio": float,                // h_n / H*, <1 means target met
      "state": "collecting" | "enough" | "diminishing" | "unreliable",
      "consecutive_ok": int,
      "patience": int,
      "advisory": true,              // constant; the user decides
      "reasons": [str]               // machine codes, e.g. "unsettled_last"
    }

State `unreliable` is emitted when a guard in section 4 trips (drift
unresolved, model misfit, cold start).

### 2.2 Suggestion payload (`NextSuggestion`)

    {
      "schema": 1, "phase": str, "job_version": int,
      "candidate_id": str,           // WS1 candidate identifier
      "x": float, "unit": str,
      "expected_gain": float,        // A(c*), same unit as half_width
      "expected_half_width": float,  // E[h_{n+1} | c*]
      "alternatives": [{"candidate_id": str, "expected_gain": float}],  // top 3
      "criterion": "target" | "d_opt" | "a_opt",
      "elapsed_ms": float,
      "budget_exceeded": bool,
      "advisory": true
    }

## 3. Candidate set

Provided by WS1 as an immutable ordered list of `{candidate_id, x, u_x}`,
already filtered for physical feasibility (weight availability, safe loads).
The selector never invents candidates and never proposes a load outside the
set. Candidates already measured and settled are not removed (replicates
are valid: they reduce noise), but gain is penalised by the hysteresis
guard (sec 4.1) for repeating a load within the same unsettled step.

## 4. Edge cases

4.1 Drift and creep. Only settled observations enter `D_n`: a point is
admitted when the settle detector reports `settled` AND the human confirms.
Unsettled readings are shown but excluded and flagged `unsettled_last`. The
creep rate (settle `slope`, a `Measured`) inflates the noise term:
`s2(c) = u_read^2 + (slope_u * t_dwell)^2`, so slow-creeping materials
yield lower gain per point and an earlier `diminishing` verdict instead of a
false "enough".

4.2 Non-linearity near yield. Elastic phase uses a rolling lack-of-fit check:
if the standardised residual of the newest point exceeds 3, or the last 3
residuals share sign with growing magnitude, the elastic design halts with
`unreliable` and `reasons=["departure_from_linear"]`, and the yield GP phase
is proposed (advisory). Elastic fit points beyond the departure are excluded
from the elastic posterior.

4.3 Curvature in calibration. Fit the quadratic extension; if the
extra-term |t| > 3 the model is promoted to quadratic (`phi = (1,d,d^2)`) and
mid-range candidates gain value automatically through `A`.

4.4 Cold start. With `n < n_min` (default 3 elastic/calibration, 5 yield) there
is no usable posterior variance. The selector falls back to a deterministic
space-filling order over the candidate set: extremes first, then the
bisection midpoints (the binary-search-like WS1 order). The indicator state is
`unreliable` with reason `cold_start`; stop is never recommended.

4.5 Computational budget. Hard budget 200 ms per suggestion on the reference
laptop. The linear phases are O(C p^2) (C candidates, p <= 3) and take
well under 10 ms for C <= 500. The GP phase is O(n^3 + C n^2): n capped at 60
(oldest non-extreme points are thinned beyond that), hyperparameters are
re-optimised only every 3 points or when the marginal likelihood drops
(warm start from the previous values, max 25 iterations), and the candidate
window of 1.3 caps C at 64. If the elapsed time passes 150 ms the loop
stops refining and returns the best candidate so far with
`budget_exceeded=true`. Runs as a cancellable job; a newer request supersedes.

## 5. Determinism

Same inputs yield bit-identical outputs. No global RNG: any stochastic step
(hyperparameter restarts) uses `numpy.random.Generator(PCG64(seed))` with
`seed = hash64(session_id, phase, n)` using a fixed algorithm (blake2b), not
Python `hash`. Candidate iteration order is the WS1 order; argmax ties go to
the lowest index. Floating point: single-threaded linear algebra
(`OPENBLAS_NUM_THREADS=1` inside the job), float64 only. Time is never an
input to the numerics; `elapsed_ms` is reported but the budget cut-off falls
back on a deterministic iteration cap (the wall clock only sets
`budget_exceeded`, and a golden test runs with the clock disabled).

## 6. Benchmark protocol (simulator-based)

Purpose: show the selector reaches the target half-width in fewer
observations than baselines. Run by GP2 ~93ZD322.

- Truth: the `sadi-sim` device simulator, with seeded scenarios: linear
  elastic (known E), elastic plus yield (known sigma_y), LVDT with curvature,
  and creep/drift and fault-injected variants. Each scenario has
  a known true `q`.
- Policies compared on the same candidate set and noise draws:
  1. `random`: uniform without replacement (replacement allowed after the set
     is exhausted), 
  2. `binary_search`: the WS1 extremes-then-midpoints order,
  3. `gp_selector` (this doc).
- Trials: 200 seeded repetitions per scenario (seed = trial index), fixed
  budget of N_max = 20 observations.
- Metrics, per policy and scenario: (a) observations to reach
  `h_n <= H*` (median, IQR; censored at N_max and reported separately);
  (b) final `|q_hat - q|` and empirical coverage of the 95% interval (must be
  within 93-97% or the run is flagged miscalibrated); (c) false-stop rate
  (stop recommended while the true error exceeds `H*`); (d) p95 suggestion
  latency, must be < 200 ms; (e) determinism: two runs bit-identical.
- Acceptance: the selector's median observations-to-target is no worse than
  both baselines in every scenario and at least 20% lower than random in the
  linear and yield scenarios, with coverage and false-stop rate (<= 5%)
  within bounds. Results are written to a JSON report and summarised in the
  GP2 ticket; a regression gate re-runs a reduced 20-trial subset in CI.

## 7. Logging and errors

Selector functions return typani `Result[T, SelectorError]`; error members:
`NoCandidates`, `SingularPosterior`, `NonFinite`, `BudgetExceeded`,
`InvalidTarget`. Each branch in sections 2 and 4 logs once at INFO with
`(phase, n, state, reasons)`, and errors at WARNING with the hint text.
