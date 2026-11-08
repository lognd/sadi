// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
// frob:ticket 01M6X9NXWB7KW3ZGQP02KDWN8N
/** Typed parsing of the JSON text side channel (docs/server/websocket.md "Messages"). */
import { err, ok, type Result } from "../api/result";

/** Settle states reported by the streaming detector. */
export type SettleState = "loading" | "creeping" | "settled";

/** Raw-seq span of the open point's capture window, as reported by the server. */
export interface CaptureWindow {
  readonly firstRawSeq: number;
  readonly lastRawSeq: number;
}

/** Server text message, discriminated by `kind`; unknown kinds are kept as "other". */
export type ServerMessage =
  | { readonly kind: "hello"; readonly latest: Readonly<Record<string, unknown>>; readonly simulated: boolean }
  | { readonly kind: "state"; readonly rawSeq: number; readonly state: SettleState | null; readonly pointIndex: number | null; readonly timeSinceLoad: number | null; readonly driftVps?: number | null; readonly window?: CaptureWindow | null; readonly simulated?: boolean }
  | { readonly kind: "result"; readonly rawSeq: number; readonly pointIndex: number | null; readonly settled: boolean; readonly forcedEarly: boolean; readonly windowEnd: number | null }
  | { readonly kind: "analysis_failed"; readonly rawSeq: number; readonly reason: string }
  | { readonly kind: "stopped"; readonly reason: string; readonly hint: string }
  | { readonly kind: "guidance"; readonly phase: string; readonly nextAction: string; readonly stopEarly: boolean; readonly stopReason: string }
  | { readonly kind: "stats"; readonly sentFrames: number; readonly droppedFrames: number }
  | { readonly kind: "other"; readonly name: string };

/** Why a text message was rejected. */
export type MessageError = "not_json" | "not_object" | "no_kind";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown, d = ""): string => (typeof v === "string" ? v : d);

/** Parse one JSON text message into a ServerMessage without throwing. */
export function parseMessage(text: string): Result<ServerMessage, MessageError> {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return err("not_json");
  }
  if (!isObj(raw)) return err("not_object");
  const kind = raw["kind"];
  if (typeof kind !== "string") return err("no_kind");
  const rawSeq = num(raw["raw_seq"]) ?? 0;
  switch (kind) {
    case "hello":
      return ok({ kind, latest: isObj(raw["latest"]) ? raw["latest"] : {}, simulated: raw["simulated"] === true });
    case "state": {
      const st = isObj(raw["status"]) ? raw["status"] : {};
      const s = st["state"];
      const state = s === "loading" || s === "creeping" || s === "settled" ? s : null;
      const w = raw["window"];
      const first = isObj(w) ? num(w["first_raw_seq"]) : null;
      const last = isObj(w) ? num(w["last_raw_seq"]) : null;
      return ok({
        kind, rawSeq, state, pointIndex: num(st["point_index"]), timeSinceLoad: num(st["time_since_load"]),
        driftVps: num(raw["drift_vps"]),
        window: first !== null && last !== null ? { firstRawSeq: first, lastRawSeq: last } : null,
        simulated: raw["simulated"] === true,
      });
    }
    case "result": {
      const rec = isObj(raw["record"]) ? raw["record"] : {};
      return ok({
        kind, rawSeq, pointIndex: num(rec["point_index"]), settled: rec["settled"] === true,
        forcedEarly: rec["forced_early"] === true, windowEnd: num(rec["window_end"]),
      });
    }
    case "analysis_failed":
      return ok({ kind, rawSeq, reason: str(raw["reason"]) });
    case "stopped":
      return ok({ kind, reason: str(raw["reason"]), hint: str(raw["hint"]) });
    case "guidance":
      return ok({ kind, phase: str(raw["phase"]), nextAction: str(raw["next_action"]), stopEarly: raw["stop_early"] === true, stopReason: str(raw["stop_reason"]) });
    case "stats":
      return ok({ kind, sentFrames: num(raw["sent_frames"]) ?? 0, droppedFrames: num(raw["dropped_frames"]) ?? 0 });
    default:
      return ok({ kind: "other", name: kind });
  }
}
