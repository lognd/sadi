// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87

/** Round a positive range to a "nice" 1/2/5 x 10^k value (floor or round the mantissa). */
function niceNum(range: number, round: boolean): number {
  const exp = Math.floor(Math.log10(range));
  const frac = range / 10 ** exp;
  let nice: number;
  if (round) nice = frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10;
  else nice = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10;
  return nice * 10 ** exp;
}

/** Tick positions and their step for a domain. */
export interface TickSet {
  readonly values: readonly number[];
  readonly step: number;
}

/** Nice 1/2/5 ticks covering [min, max] with roughly `target` ticks; degenerate ranges are widened. */
export function niceTicks(min: number, max: number, target = 6): TickSet {
  let lo = min;
  let hi = max;
  if (!(hi > lo)) {
    const pad = lo === 0 ? 1 : Math.abs(lo) * 0.1;
    lo -= pad;
    hi += pad;
  }
  const step = niceNum(niceNum(hi - lo, false) / Math.max(target - 1, 1), true);
  const start = Math.floor(lo / step + 1e-9);
  const end = Math.ceil(hi / step - 1e-9);
  const decimals = Math.min(12, Math.max(0, -Math.floor(Math.log10(step)) + 1));
  const values: number[] = [];
  for (let i = start; i <= end; i++) values.push(Number((i * step).toFixed(decimals)));
  return { values, step };
}

/** Format a tick value given the tick step: fixed decimals normally, exponent form for extremes. */
export function formatTick(value: number, step: number): string {
  if (value === 0 || Math.abs(value) < step * 1e-9) return "0";
  const abs = Math.abs(value);
  if (abs >= 1e6 || abs < 1e-3) {
    const digits = Math.max(0, Math.min(6, Math.floor(Math.log10(abs)) - Math.floor(Math.log10(step))));
    return value.toExponential(digits).replace("e+", "e");
  }
  const decimals = Math.min(10, Math.max(0, -Math.floor(Math.log10(step))));
  return value.toFixed(decimals);
}

/** Decade ticks for a log axis: tick values plus the decade-snapped bounds that cover [min, max]. */
export interface LogTickSet {
  readonly values: readonly number[];
  readonly lo: number;
  readonly hi: number;
}

/**
 * Decade ticks (1 x 10^k) covering the positive range [min, max]; spans of two decades or less also
 * get 2 and 5 minor labels, and spans over seven decades are strided so labels stay readable.
 * Callers must pass min > 0 (validateScene reports non-positive data as an error first).
 */
export function logTicks(min: number, max: number): LogTickSet {
  const e0 = Math.floor(Math.log10(min) + 1e-9);
  let e1 = Math.ceil(Math.log10(max) - 1e-9);
  if (e1 <= e0) e1 = e0 + 1;
  const decades = e1 - e0;
  const stride = Math.max(1, Math.ceil(decades / 7));
  const mantissas = decades <= 2 ? [1, 2, 5] : [1];
  const values: number[] = [];
  for (let e = e0; e <= e1; e += stride) {
    for (const m of mantissas) {
      const v = Number((m * 10 ** e).toPrecision(12));
      if (v <= 10 ** e1 * (1 + 1e-9)) values.push(v);
    }
  }
  return { values, lo: Number((10 ** e0).toPrecision(12)), hi: Number((10 ** e1).toPrecision(12)) };
}
