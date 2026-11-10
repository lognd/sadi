// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
/** Pure derivation of what the run screen shows from the live snapshot, connection and settle state. */
import { SATURATION_V } from "../../plots/live/scene";
import type { Snapshot } from "../../plots/live/window";
import type { Motion, Signal, Source } from "../../components/status/StatusBar";
import type { ConnState } from "../../ws/client";
import type { SettleState } from "../../ws/messages";

/** Fraction of the range at which the signal is "near limit" (docs/ux.md section 5). */
export const NEAR_LIMIT_FRACTION = 0.9;
/** Seconds of recent trace used for the saturation check and the drift estimate. */
export const RECENT_S = 1;
/** Milliseconds without a frame after which the readout counts as idle (not live). */
export const IDLE_FRAME_MS = 2000;

/** Everything the readouts and status bar need. */
export interface LiveView {
  /** Latest voltage (centre of the newest column), or null before any data. */
  readonly volts: number | null;
  /** Client-side drift estimate over the last second, V/s, or null when too little data. */
  readonly driftVps: number | null;
  readonly signal: Signal;
  readonly motion: Motion;
  readonly source: Source;
  /** True when the data on screen lags the instrument (disconnected or flagged stale). */
  readonly stale: boolean;
  /** True when no frame arrived recently: readings are cleared rather than shown as live. */
  readonly idle?: boolean;
  /** Recent mean / sd / count used for tare values the operator should not have to type; null when idle or too little data. */
  readonly recent?: RecentStats | null;
}

/** Mean, sample standard deviation and column count of the recent trace (basis of the tare). */
export interface RecentStats {
  readonly mean: number;
  readonly sd: number;
  readonly n: number;
}

/** Statistics of the mid line over the last RECENT_S seconds; null with fewer than 2 columns. */
export function recentStats(s: Snapshot): RecentStats | null {
  let n = 0, sum = 0, sumSq = 0;
  for (let i = 0; i < s.x.length; i++) {
    if ((s.x[i] as number) < s.t1 - RECENT_S) continue;
    const v = s.mid[i] as number;
    n++; sum += v; sumSq += v * v;
  }
  if (n < 2) return null;
  const mean = sum / n;
  return { mean, sd: Math.sqrt(Math.max(0, (sumSq - n * mean * mean) / (n - 1))), n };
}

/** Slope (V/s) of `mid` against `x` over columns at or after `from`; null with fewer than 3 columns. */
export function driftOver(x: Float64Array, mid: Float64Array, from: number): number | null {
  let n = 0, sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (let i = 0; i < x.length; i++) {
    const xi = x[i] as number;
    if (xi < from) continue;
    const yi = mid[i] as number;
    n++; sx += xi; sy += yi; sxx += xi * xi; sxy += xi * yi;
  }
  const den = n * sxx - sx * sx;
  return n < 3 || den <= 0 ? null : (n * sxy - sx * sy) / den;
}

/** Signal level from the recent envelope: saturated at the rail, near-limit at 90 % of range. */
export function signalOf(s: Snapshot): Signal {
  let peak = 0;
  for (let i = 0; i < s.x.length; i++) {
    if ((s.x[i] as number) < s.t1 - RECENT_S) continue;
    peak = Math.max(peak, Math.abs(s.hi[i] as number), Math.abs(s.lo[i] as number));
  }
  if (peak >= SATURATION_V) return "saturated";
  return peak >= NEAR_LIMIT_FRACTION * SATURATION_V ? "near-limit" : "ok";
}

/** Status-bar source: any non-open connection is Disconnected, otherwise Simulated or Connected. */
export function sourceOf(c: ConnState, simulated: boolean): Source {
  if (c.status !== "open") return "disconnected";
  return simulated ? "simulated" : "connected";
}

/** Status-bar motion from the server settle state; "loading" (no load/too few samples) is unknown, never creeping. */
export function motionOf(st: SettleState | null): Motion {
  if (st === null || st === "loading") return "unknown";
  return st === "settled" ? "settled" : "creeping";
}

/** Combine the trace snapshot, connection and latest settle state into one view; server drift wins over the client estimate. */
export function deriveLive(
  snap: Snapshot, conn: ConnState, settle: SettleState | null, simulated: boolean, serverDriftVps: number | null = null,
  frameAgeMs: number | null = null,
): LiveView {
  const n = snap.x.length;
  const idle = frameAgeMs !== null && frameAgeMs > IDLE_FRAME_MS;
  const drift = idle ? null : (serverDriftVps ?? driftOver(snap.x, snap.mid, snap.t1 - RECENT_S));
  return {
    volts: n === 0 || idle ? null : (snap.mid[n - 1] as number),
    driftVps: drift !== null && Number.isFinite(drift) ? drift : null,
    signal: idle ? "ok" : signalOf(snap),
    motion: idle ? "unknown" : motionOf(settle),
    source: sourceOf(conn, simulated),
    stale: idle || conn.status !== "open" || snap.stale,
    idle,
    recent: idle ? null : recentStats(snap),
  };
}
