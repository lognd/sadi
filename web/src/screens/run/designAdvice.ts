// frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
// frob:ticket 01M72VM5X86QRPEWSW65Q9RBD8
// frob:ticket 01M72YPB58KPZ9WR5BE2Q852YF
// frob:accept COV001 because="covered by SuggestedWeightPanel.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { getJson, type ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import type { Result } from "../../api/result";
import type { components } from "../../api/schema";

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

/** Server reason code, generated from the OpenAPI schema so a rename breaks tsc here. */
// frob:ticket 01M72YKEYW6QFR5YTFSV2YBKMJ
export type ReasonCode = components["schemas"]["ConfidenceIndicator"]["reasons"][number];

/** "Enough data" indicator from the server (the fields the UI reads). */
export interface DesignIndicator {
  readonly n: number;
  readonly state: "collecting" | "enough" | "diminishing" | "unreliable";
  readonly ratio: number | null;
  readonly consecutive_ok: number;
  readonly patience: number;
  readonly reasons: readonly ReasonCode[];
}

/** Whole advice payload. */
export interface DesignAdvice { readonly suggestion: DesignSuggestion | null; readonly indicator: DesignIndicator }

/** Fetch the advisory next weight and enough-data indicator (read-only). */
export function getDesignAdvice(phase: string, fetchImpl: typeof fetch = fetch): Promise<Result<DesignAdvice, ApiError>> {
  log.debug("fetch design advice", { phase });
  return getJson<DesignAdvice>(`/api/design/next-weight?phase=${encodeURIComponent(phase)}`, fetchImpl);
}

/** Plain-language text for one reason code; exhaustive so a new server code fails tsc. */
function reasonText(r: ReasonCode, i: DesignIndicator): string | null {
  switch (r) {
    case "no_elastic_fit": return "Take at least 3 elastic points first; the yield suggestion needs the straight-line fit.";
    case "no_calibration": return "No LVDT calibration was recorded, so the yield offset cannot be worked out. Choose loads yourself.";
    case "cold_start": return `Keep going: collect a few more points first (you have ${String(i.n)}).`;
    case "departure_from_linear": return "The last point is off the straight line. Check it before adding more.";
    case "range_exhausted": return "You have reached the top of the elastic range; finish this step.";
    case "yield_not_reached": return "The curve has not bent over yet. Try a heavier load.";
    case "singular": return "The points so far cannot be fitted (they are too alike). Try a clearly different load.";
    case "no_offset": return "The yield offset cannot be worked out yet. Choose loads yourself.";
    case "diminishing_returns": return null; // falls through to the state wording ("Nearly there")
  }
}

/** Reason precedence, highest first; the first present reason with text wins. */
const REASON_ORDER: readonly ReasonCode[] = ["no_elastic_fit", "no_calibration", "cold_start", "singular", "no_offset", "departure_from_linear", "range_exhausted", "yield_not_reached", "diminishing_returns"];

/** Plain-language reading of the indicator for a student. */
export function indicatorText(i: DesignIndicator): string {
  for (const r of REASON_ORDER) {
    if (!i.reasons.includes(r)) continue;
    const t = reasonText(r, i);
    if (t !== null) return t;
  }
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
