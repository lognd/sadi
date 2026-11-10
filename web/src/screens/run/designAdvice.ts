// frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
// frob:ticket 01M72VM5X86QRPEWSW65Q9RBD8
// frob:ticket 2Q852YF
// frob:accept COV001 because="covered by SuggestedWeightPanel.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { getJson, type ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import type { Result } from "../../api/result";

const log = getLogger("screens.run.designAdvice");

/** One runner-up load. */
export interface DesignAlt { readonly candidate_id: string; readonly x: number; readonly expected_gain: number }

/** Advisory next-load suggestion from GET /api/design/next-weight. */
export interface DesignSuggestion {
  readonly x: number;
  readonly unit: string;
  readonly expected_gain: number;
  readonly alternatives: readonly DesignAlt[];
  readonly why: string;
}

/** "Enough data" indicator from the server. */
export interface DesignIndicator {
  readonly n: number;
  readonly state: "collecting" | "enough" | "diminishing" | "unreliable";
  readonly ratio: number | null;
  readonly consecutive_ok: number;
  readonly patience: number;
  readonly reasons: readonly string[];
}

/** Whole advice payload. */
export interface DesignAdvice { readonly suggestion: DesignSuggestion | null; readonly indicator: DesignIndicator }

/** Fetch the advisory next weight and enough-data indicator (read-only). */
export function getDesignAdvice(phase: string, fetchImpl: typeof fetch = fetch): Promise<Result<DesignAdvice, ApiError>> {
  log.debug("fetch design advice", { phase });
  return getJson<DesignAdvice>(`/api/design/next-weight?phase=${encodeURIComponent(phase)}`, fetchImpl);
}

/** Plain-language reading of the indicator for a student. */
export function indicatorText(i: DesignIndicator): string {
  if (i.reasons.includes("no_elastic_fit")) return "Take at least 3 elastic points first; the yield suggestion needs the straight-line fit.";
  if (i.reasons.includes("no_calibration")) return "No LVDT calibration was recorded, so the yield offset cannot be worked out. Choose loads yourself.";
  if (i.reasons.includes("cold_start")) return `Keep going: collect a few more points first (you have ${String(i.n)}).`;
  if (i.reasons.includes("departure_from_linear")) return "The last point is off the straight line. Check it before adding more.";
  if (i.reasons.includes("range_exhausted")) return "You have reached the top of the elastic range; finish this step.";
  if (i.reasons.includes("yield_not_reached")) return "The curve has not bent over yet. Try a heavier load.";
  switch (i.state) {
    case "enough": return "Enough data: more points will barely improve the result. You can stop (your call).";
    case "diminishing": return "Nearly there: extra points now help very little.";
    case "unreliable": return "Not reliable yet: the data does not fit the model well.";
    default: return `Keep going: ${String(i.consecutive_ok)} of ${String(i.patience)} good checks so far.`;
  }
}

/** Format a load in kg and newtons, or a gauge height in the field unit (m) with mm in parentheses. */
export function loadText(x: number, unit: string): string {
  if (unit === "kg") return `${x.toFixed(2)} kg (${(x * 9.80665).toFixed(1)} N)`;
  return unit === "m" ? `${x.toFixed(4).replace(/0$/, "")} m (${String(Number((x * 1000).toFixed(1)))} mm)` : `${x.toPrecision(3)} ${unit}`;
}
