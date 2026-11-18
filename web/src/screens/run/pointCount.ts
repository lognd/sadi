// frob:ticket 01M7274EKWS410XEGZGFD6HWHK
/** Accepted-point counting and the Finish gate for a run step (data is never touched; this only informs the UI). */
import type { PointView } from "../review/types";
import { PHASES, type RunPhase } from "./phases";

/** Count the non-excluded points captured for a run phase. */
export function countPhasePoints(points: readonly PointView[], phase: RunPhase): number {
  const api = PHASES[phase].apiPhase;
  return points.filter((p) => p.phase === api && !p.excluded).length;
}

/** Plain reason Finish is disabled, or null when the minimum point count is met (or still unknown). */
export function finishBlockedWhy(phase: RunPhase, count: number | null): string | null {
  if (count === null) return null;
  const need = PHASES[phase].minPoints;
  if (count >= need) return null;
  const left = need - count;
  return `Accept at least ${String(need)} points first (${String(count)} so far, ${String(left)} to go).`;
}
