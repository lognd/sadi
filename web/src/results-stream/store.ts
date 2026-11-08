// frob:ticket 01M6W7RB0GPGHTABW7P4XEGRNJ
// frob:accept COV001 because="covered by results-stream.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
/** Pure results-stream state: latest envelope per key plus the newest data version seen. */
import { getLogger } from "../api/log";
import type { ResultEnvelope } from "./envelope";

const log = getLogger("results-stream.store");

/** Reducer state. */
export interface StreamState {
  readonly latestDataVersion: number;
  readonly byKey: Readonly<Record<string, ResultEnvelope>>;
}

/** Empty state before any envelope arrives. */
export const EMPTY_STATE: StreamState = { latestDataVersion: -1, byKey: {} };

/** Fold one envelope in; out-of-order (result_version not newer) envelopes are dropped. */
export function applyEnvelope(s: StreamState, e: ResultEnvelope): StreamState {
  const cur = s.byKey[e.key];
  if (cur !== undefined && e.resultVersion <= cur.resultVersion) {
    log.warn("dropping out-of-order envelope", { key: e.key, got: e.resultVersion, have: cur.resultVersion });
    return s;
  }
  const latestDataVersion = Math.max(s.latestDataVersion, e.dataVersion);
  log.debug("envelope applied", { key: e.key, state: e.state, dataVersion: e.dataVersion, latestDataVersion });
  return { latestDataVersion, byKey: { ...s.byKey, [e.key]: e } };
}

/** True when the value must carry the stale marker: server-stale or older than the newest data. */
export function isStale(s: StreamState, e: ResultEnvelope): boolean {
  return e.state === "stale" || e.dataVersion < s.latestDataVersion;
}

/** True while MC/GP refinement is still running for this value (and it is not stale). */
export function isRefining(s: StreamState, e: ResultEnvelope): boolean {
  return e.state === "refining" && !isStale(s, e);
}
