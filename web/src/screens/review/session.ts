// frob:ticket ~FHNEDX8
// frob:accept COV001 because="covered by ReviewScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { getLogger } from "../../api/log";
import type { ApiError } from "../../api/client";
import type { Result } from "../../api/result";
import type { ResultSet } from "../../components/results/types";
import { describeProblem, getHistory, getPoints, getResults } from "./api";
import type { Committed, HistoryState, PointView } from "./types";

const log = getLogger("screens.review.session");

/** Everything the screen shows; replaced wholesale after each refresh. */
export interface ReviewData {
  points: PointView[];
  history: HistoryState;
  results: ResultSet | null;
}

/** Outcome of an action: fresh data on success, or the previous data plus a message. */
export interface ActionOutcome {
  data: ReviewData;
  error: string | null;
  note: string | null;
}

/** Load points, history and recomputed results; results may be unavailable (pending) without failing the load. */
export async function loadReview(f?: typeof fetch): Promise<{ data: ReviewData | null; error: string | null }> {
  const [p, h, r] = await Promise.all([getPoints(f), getHistory(f), getResults(f)]);
  if (!p.ok) return { data: null, error: describeProblem(p.error) };
  if (!h.ok) return { data: null, error: describeProblem(h.error) };
  if (!r.ok) log.warn("results recompute unavailable", { kind: r.error.kind });
  return { data: { points: p.value, history: h.value, results: r.ok ? r.value : null }, error: null };
}

/** Run a write, then refresh everything from the server (raw recompute); on failure keep `prev` untouched. */
export async function runAction(
  prev: ReviewData,
  write: () => Promise<Result<Committed, ApiError>>,
  f?: typeof fetch,
): Promise<ActionOutcome> {
  const w = await write();
  if (!w.ok) {
    log.warn("action refused; data unchanged", { kind: w.error.kind });
    return { data: prev, error: describeProblem(w.error), note: null };
  }
  log.info("action committed", { seq: w.value.seq, summary: w.value.summary });
  const l = await loadReview(f);
  if (l.data === null) {
    return { data: prev, error: `Saved, but the refresh failed. ${l.error ?? ""}`.trim(), note: w.value.summary };
  }
  return { data: l.data, error: null, note: w.value.summary };
}
