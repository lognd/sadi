// frob:ticket 01M720QDN33FYFXX1SZ66Y1FQW
// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
/** Capture decision (accept / forced-early confirmation / blocked) and the POST to /api/session/points. */
import type { ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import type { Result } from "../../api/result";
import type { Committed } from "../review/types";
import { postJson } from "../review/api";
import type { LiveView } from "./live";
import { PHASES, type RunPhase } from "./phases";

const log = getLogger("screens.run.capture");

/** What pressing an accept key should do right now. */
export type Decision =
  | { readonly kind: "capture"; readonly forcedEarly: false }
  | { readonly kind: "confirm-early" }
  | { readonly kind: "capture-early" }
  | { readonly kind: "blocked"; readonly why: string };

/** Pending forced-early confirmation state. */
export type Confirm = "idle" | "asking";

const WHY = {
  disconnected: "The instrument stream is disconnected. Wait for it to reconnect; saved data is untouched.",
  saturated: "The reading is at its limit (saturated). Lower the load, then try again.",
  creeping: "The reading is still moving. Wait for Settled, or press Shift+Space to accept early.",
  unknown: "Not enough data yet. Wait for the reading to appear.",
  idle: "No live readings are arriving (idle). Start the run or reconnect the instrument; capture is paused.",
} as const;

/** Decide the outcome of an accept key; saturation and disconnect block even a forced capture. */
export function decide(view: LiveView, early: boolean, confirm: Confirm): Decision {
  if (view.source === "disconnected") return { kind: "blocked", why: WHY.disconnected };
  if (view.idle === true) return { kind: "blocked", why: WHY.idle };
  if (view.signal === "saturated") return { kind: "blocked", why: WHY.saturated };
  if (view.volts === null) return { kind: "blocked", why: WHY.unknown };
  if (!early) {
    return view.motion === "settled" ? { kind: "capture", forcedEarly: false } : { kind: "blocked", why: WHY.creeping };
  }
  if (view.motion === "settled") return { kind: "capture", forcedEarly: false };
  return confirm === "asking" ? { kind: "capture-early" } : { kind: "confirm-early" };
}

/** Request body of POST /api/session/points (CaptureBody). */
export interface CaptureBody {
  readonly phase: string;
  readonly inputs: Readonly<Record<string, unknown>>;
  readonly window: { readonly first_raw_seq: number; readonly last_raw_seq: number };
  readonly settled: boolean;
  readonly forced_early: boolean;
  readonly drift_rate: number | null;
  /** Idempotency key: a retried accept reuses it so the server never records the point twice. */
  readonly request_id?: string;
}

/** A fresh idempotency key for one accept attempt. */
export function newRequestId(): string {
  return globalThis.crypto.randomUUID();
}

/** Hint shown when a second accept arrives before the load was changed. */
export const WHY_SAME_LOAD = "This load is already recorded. Change the load or gauge block, then click the mark button, before accepting again.";

/** Build the capture body. `rawSeq` is the newest raw seq seen on the stream (see docs gap G1). */
export function buildBody(phase: RunPhase, inputs: Readonly<Record<string, unknown>>, rawSeq: number, view: LiveView, early: boolean, requestId?: string): CaptureBody {
  return {
    phase: PHASES[phase].apiPhase, inputs,
    window: { first_raw_seq: rawSeq, last_raw_seq: rawSeq },
    settled: !early, forced_early: early, drift_rate: view.driftVps,
    ...(requestId === undefined ? {} : { request_id: requestId }),
  };
}

/** POST one capture; returns the committed state or the API error. */
export async function postCapture(body: CaptureBody, f: typeof fetch = fetch): Promise<Result<Committed, ApiError>> {
  log.info("capture", { phase: body.phase, forced: body.forced_early });
  const r = await postJson<Committed>("/api/session/points", body, f);
  if (!r.ok) log.warn("capture refused", { kind: r.error.kind });
  return r;
}

/** Build the `specimen` point body (geometry entered alongside a phase); same window/settle as the phase point. */
export function buildSpecimenBody(inputs: Readonly<Record<string, unknown>>, rawSeq: number, view: LiveView): CaptureBody {
  return {
    phase: "specimen", inputs,
    window: { first_raw_seq: rawSeq, last_raw_seq: rawSeq },
    settled: true, forced_early: false, drift_rate: view.driftVps,
  };
}

const UUID_RE = /\s*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

/** User-facing "Captured: ..." line from a commit summary, with raw UUIDs removed. */
export function capturedMessage(summary: string): string {
  const clean = summary.replace(UUID_RE, "").trim();
  return clean === "" || clean === "captured" ? "Captured." : `Captured: ${clean}`;
}
