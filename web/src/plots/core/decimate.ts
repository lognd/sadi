// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
import type { Column } from "./scene";

/**
 * Min/max decimation: pick indices so a series of any length draws as at most
 * 2*buckets + 2 vertices while preserving every visual extreme. Non-finite points are skipped.
 * Returns ascending indices; the identity range when the series is already small.
 */
export function decimateIndices(x: Column, y: Column, buckets: number): number[] {
  const n = Math.min(x.length, y.length);
  const nb = Math.max(1, Math.floor(buckets));
  if (n <= nb * 2 + 2) {
    const all: number[] = [];
    for (let i = 0; i < n; i++) all.push(i);
    return all;
  }
  let x0 = Infinity;
  let x1 = -Infinity;
  for (let i = 0; i < n; i++) {
    const xv = x[i] as number;
    if (!Number.isFinite(xv)) continue;
    if (xv < x0) x0 = xv;
    if (xv > x1) x1 = xv;
  }
  const span = x1 - x0;
  const lo = new Int32Array(nb).fill(-1);
  const hi = new Int32Array(nb).fill(-1);
  let first = -1;
  let last = -1;
  for (let i = 0; i < n; i++) {
    const xv = x[i] as number;
    const yv = y[i] as number;
    if (!Number.isFinite(xv) || !Number.isFinite(yv)) continue;
    if (first < 0) first = i;
    last = i;
    const b = span > 0 ? Math.min(nb - 1, Math.floor(((xv - x0) / span) * nb)) : 0;
    const l = lo[b] as number;
    if (l < 0) {
      lo[b] = i;
      hi[b] = i;
    } else {
      if (yv < (y[l] as number)) lo[b] = i;
      if (yv > (y[hi[b] as number] as number)) hi[b] = i;
    }
  }
  const out: number[] = [];
  const push = (i: number): void => {
    if (i >= 0 && out[out.length - 1] !== i) out.push(i);
  };
  push(first);
  for (let b = 0; b < nb; b++) {
    const a = lo[b] as number;
    const c = hi[b] as number;
    if (a < 0) continue;
    if (a <= c) {
      push(a);
      push(c);
    } else {
      push(c);
      push(a);
    }
  }
  push(last);
  return out.sort((p, q) => p - q).filter((v, k, arr) => k === 0 || arr[k - 1] !== v);
}
