// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
// frob:ticket 01M6XA21KQE5WEXAN39683H4S9
import { getJson, type ApiError } from "../../api/client";
import { err, ok, type Result } from "../../api/result";
import type { components } from "../../api/schema";
import type { Committed } from "../review/types";
import { postCapture, type CaptureBody } from "../run/capture";

export type ClampStatus = components["schemas"]["ClampStatus"];

/** One cycle as the operator enters it (strings straight from the form fields). */
export interface CycleFields {
  readonly zeroBefore: string;
  readonly zeroAfter: string;
  readonly slips: string;
}

/** Typed cycle inputs sent with the capture (names match the backend ClampInputs). */
export type CycleInputs = {
  readonly zero_before: number;
  readonly zero_after: number;
  readonly slip_events: number;
};

/** Parse the form fields into cycle inputs; Err is a sentence saying what to fix. */
export function parseCycle(f: CycleFields): Result<CycleInputs, string> {
  // Calibration comes after this step, so a strain reading may not exist yet: blank means 0.
  const zb = f.zeroBefore.trim() === "" ? 0 : Number(f.zeroBefore);
  const za = f.zeroAfter.trim() === "" ? 0 : Number(f.zeroAfter);
  if (!Number.isFinite(zb)) return err("The reading before loading must be a number (or blank for 0).");
  if (!Number.isFinite(za)) return err("The reading after unloading must be a number (or blank for 0).");
  const slips = f.slips.trim() === "" ? 0 : Number(f.slips);
  if (!Number.isInteger(slips) || slips < 0) return err("Slips seen must be a whole number, 0 or more.");
  return ok({ zero_before: zb, zero_after: za, slip_events: slips });
}

/** Capture body for one clamp cycle; there is no raw window for a typed-in cycle. */
export function cycleBody(inputs: CycleInputs): CaptureBody {
  return {
    phase: "setup", inputs,
    window: { first_raw_seq: 0, last_raw_seq: 0 },
    settled: true, forced_early: false, drift_rate: null,
  };
}

/** Fetch the clamp-check procedure, recorded cycles and verdict. */
export const getClampStatus = (f?: typeof fetch): Promise<Result<ClampStatus, ApiError>> =>
  getJson<ClampStatus>("/api/session/clamp-check", f);

/** Append one cycle capture (never overwrites an earlier cycle). */
export const captureCycle = (inputs: CycleInputs, f?: typeof fetch): Promise<Result<Committed, ApiError>> =>
  postCapture(cycleBody(inputs), f);
