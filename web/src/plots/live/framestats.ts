// frob:ticket 01M6WV6TH775MHY7HHMND4Z97Z
/** Pure frame-time statistics for the live-trace 60 fps benchmark. */

/** Summary of a run of frame intervals (milliseconds). */
export interface FrameStats {
  readonly frames: number;
  readonly meanMs: number;
  readonly p95Ms: number;
  readonly p99Ms: number;
  readonly maxMs: number;
  readonly fps: number;
  readonly droppedFrames: number;
}

/** Frame budget at 60 fps in milliseconds. */
export const BUDGET_60_MS = 1000 / 60;

/** Convert ascending-or-not timestamps (ms) to successive intervals. */
export function intervals(stamps: readonly number[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < stamps.length; i++) out.push((stamps[i] as number) - (stamps[i - 1] as number));
  return out;
}

/** Nearest-rank percentile (q in [0,1]) of `xs`; NaN when empty. */
export function percentile(xs: readonly number[], q: number): number {
  if (xs.length === 0) return Number.NaN;
  const s = [...xs].sort((a, b) => a - b);
  const rank = Math.min(s.length - 1, Math.max(0, Math.ceil(q * s.length) - 1));
  return s[rank] as number;
}

/** Summarise frame intervals; a frame counts as dropped when it spans over 1.5 budgets. */
export function summarize(dts: readonly number[], budgetMs: number = BUDGET_60_MS): FrameStats {
  const n = dts.length;
  if (n === 0) {
    return { frames: 0, meanMs: Number.NaN, p95Ms: Number.NaN, p99Ms: Number.NaN, maxMs: Number.NaN, fps: Number.NaN, droppedFrames: 0 };
  }
  const total = dts.reduce((a, b) => a + b, 0);
  const mean = total / n;
  let dropped = 0;
  for (const d of dts) if (d > budgetMs * 1.5) dropped += Math.max(1, Math.round(d / budgetMs) - 1);
  return {
    frames: n, meanMs: mean, p95Ms: percentile(dts, 0.95), p99Ms: percentile(dts, 0.99),
    maxMs: Math.max(...dts), fps: 1000 / mean, droppedFrames: dropped,
  };
}

/** True when the run sustains 60 fps: mean fps >= 58 and p95 interval within 1.25 budgets. */
export function meets60fps(s: FrameStats): boolean {
  return s.frames > 0 && s.fps >= 58 && s.p95Ms <= BUDGET_60_MS * 1.25;
}
