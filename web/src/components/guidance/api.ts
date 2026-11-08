// frob:ticket 01M6W7RAPKVH796SZ6Z9EFDXQE
// frob:accept COV001 because="covered by GuidancePanel.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { getJson, type ApiError } from "../../api/client";
import type { Result } from "../../api/result";
import type { GuidancePhase, GuidanceState, HoldState } from "./types";

/** Query options for the guidance endpoint; `target` is a relative half-width fraction. */
export interface GuidanceQuery {
  phase?: GuidancePhase;
  hold?: HoldState;
  target?: number;
}

/** Build the guidance URL, omitting unset parameters. */
export function guidanceUrl(q: GuidanceQuery): string {
  const p = new URLSearchParams();
  if (q.phase !== undefined) p.set("phase", q.phase);
  if (q.hold !== undefined) p.set("hold", q.hold);
  if (q.target !== undefined) p.set("target", String(q.target));
  const s = p.toString();
  return s ? `/api/results/guidance?${s}` : "/api/results/guidance";
}

/** Fetch guidance (GET /api/results/guidance); a 409 or 422 comes back as an http error Result. */
export function getGuidance(
  q: GuidanceQuery = {},
  fetchImpl: typeof fetch = fetch,
): Promise<Result<GuidanceState, ApiError>> {
  return getJson<GuidanceState>(guidanceUrl(q), fetchImpl);
}
