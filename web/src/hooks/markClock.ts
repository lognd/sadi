// frob:ticket 01M6WV6TFKP2396PW58G1WJD3B
import { getLogger } from "../api/log";

const log = getLogger("hooks.markClock");

/**
 * Stream-clock position of a load change from `status.time_since_load`.
 * Trace frames (t0_s) and record `window_end` share one clock (sample time); `time_since_load` is a
 * duration (last sample - load time), so the load time is `now - since`. Error is below one bucket.
 */
export function loadMarkTime(now: number, timeSinceLoad: number | null): number {
  const t = now - (timeSinceLoad ?? 0);
  log.debug("load mark", { now, timeSinceLoad, t });
  return t;
}

/** Stream-clock position of a result mark: `window_end` is already stream time; fall back to now. */
export function resultMarkTime(now: number, windowEnd: number | null): number {
  return windowEnd ?? now;
}
