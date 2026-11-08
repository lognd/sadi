// frob:ticket 01M6W7RB0GPGHTABW7P4XEGRNJ
// frob:accept COV001 because="covered by results-stream.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
/** Typed parsing of the versioned ResultEnvelope (docs/server/results-stream.md). */
import { err, ok, type Result } from "../api/result";

/** Wire protocol version this client understands. */
export const PROTOCOL_VERSION = 1;

/** Envelope lifecycle state. */
export type EnvelopeState = "analytic" | "refining" | "final" | "stale";

/** One versioned result as published by the server. */
export interface ResultEnvelope {
  readonly key: string;
  readonly dataVersion: number;
  readonly resultVersion: number;
  readonly state: EnvelopeState;
  /** Refinement progress 0..1. */
  readonly progress: number;
  readonly value: unknown;
}

/** Why an envelope was rejected. */
export type EnvelopeError = "not_json" | "not_object" | "bad_protocol" | "bad_field";

const STATES: readonly string[] = ["analytic", "refining", "final", "stale"];
const isInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;

/** Parse one JSON envelope (snake_case wire form) without throwing. */
export function parseEnvelope(text: string): Result<ResultEnvelope, EnvelopeError> {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return err("not_json");
  }
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return err("not_object");
  const o = raw as Record<string, unknown>;
  if (o["protocol_version"] !== PROTOCOL_VERSION) return err("bad_protocol");
  const { key, data_version: dv, result_version: rv, state, progress } = o;
  if (typeof key !== "string" || !isInt(dv) || !isInt(rv)) return err("bad_field");
  if (typeof state !== "string" || !STATES.includes(state)) return err("bad_field");
  if (typeof progress !== "number" || !(progress >= 0 && progress <= 1)) return err("bad_field");
  return ok({ key, dataVersion: dv, resultVersion: rv, state: state as EnvelopeState, progress, value: o["value"] });
}
