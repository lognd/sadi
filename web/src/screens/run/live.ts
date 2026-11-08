// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
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

/** Status-bar motion from the server settle state; "loading" counts as not settled. */
export function motionOf(st: SettleState | null): Motion {
  if (st === null) return "unknown";
  return st === "settled" ? "settled" : "creeping";
}

/** Combine the trace snapshot, connection and latest settle state into one view; server drift wins over the client estimate. */
export function deriveLive(
  snap: Snapshot, conn: ConnState, settle: SettleState | null, simulated: boolean, serverDriftVps: number | null = null,
): LiveView {
  const n = snap.x.length;
  return {
    volts: n === 0 ? null : (snap.mid[n - 1] as number),
    driftVps: serverDriftVps ?? driftOver(snap.x, snap.mid, snap.t1 - RECENT_S),
    signal: signalOf(snap),
    motion: motionOf(settle),
    source: sourceOf(conn, simulated),
    stale: conn.status !== "open" || snap.stale,
  };
}
