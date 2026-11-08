// frob:ticket 01M6X241EV9Z0JS4TCJPQBZCCN
/** Per-phase typed capture inputs (SI units) mirroring python/sadi/core/point_inputs.py parse_inputs. */
import type { Result } from "../../api/result";
import { err, ok } from "../../api/result";
import type { RunPhase } from "./phases";

/** One operator-entered capture field. */
export interface InputField {
  /** Key sent in the capture `inputs` (the backend's name). */
  readonly key: string;
  readonly label: string;
  /** SI unit shown beside the label ("" for a count). */
  readonly unit: string;
  /** Required fields must be filled; optional blanks are omitted (the backend defaults them). */
  readonly required: boolean;
  /** Whole number only. */
  readonly integer?: boolean;
  /** Smallest accepted value. */
  readonly min?: number;
  /** Blank means "use the live block-mean reading" (shown as the placeholder). */
  readonly live?: boolean;
}

const LIVE_V: InputField = { key: "volts", label: "Volts", unit: "V", required: false, live: true };

/** Input fields per run phase; keys match parse_inputs (calibration, tare, load). */
export const PHASE_FIELDS: Readonly<Record<RunPhase, readonly InputField[]>> = {
  calibrate: [LIVE_V, { key: "height", label: "Gauge height", unit: "m", required: true, min: 0 }],
  tare: [
    { key: "mean", label: "Mean volts", unit: "V", required: false, live: true },
    { key: "n", label: "Sample count n", unit: "", required: true, integer: true, min: 1 },
    { key: "sd", label: "Volts sd", unit: "V", required: false, min: 0 },
  ],
  elastic: [LIVE_V, { key: "mass_kg", label: "Total hanging mass", unit: "kg", required: true, min: 0 }, { key: "u_mass_kg", label: "Mass uncertainty", unit: "kg", required: false, min: 0 }],
  plastic: [LIVE_V, { key: "mass_kg", label: "Total hanging mass", unit: "kg", required: true, min: 0 }, { key: "u_mass_kg", label: "Mass uncertainty", unit: "kg", required: false, min: 0 }],
};

/** Parse one raw field text; Err is a clear operator message. Blank optional gives null. */
function parseField(f: InputField, raw: string, liveVolts: number | null): Result<number | null, string> {
  const t = raw.trim();
  if (t === "") {
    if (f.live === true) {
      return liveVolts === null ? err(`${f.label}: no live reading yet; enter a value in ${f.unit}.`) : ok(liveVolts);
    }
    return f.required ? err(`${f.label} is required${f.unit ? ` (${f.unit})` : ""}.`) : ok(null);
  }
  const x = Number(t);
  if (!Number.isFinite(x)) return err(`${f.label} must be a number${f.unit ? ` in ${f.unit}` : ""}, got "${t}".`);
  if (f.integer === true && !Number.isInteger(x)) return err(`${f.label} must be a whole number, got "${t}".`);
  if (f.min !== undefined && x < f.min) return err(`${f.label} must be at least ${String(f.min)}${f.unit ? ` ${f.unit}` : ""}.`);
  return ok(x);
}

/** Validate all fields of a phase; Err lists every problem so none is hidden. */
export function collectInputs(
  phase: RunPhase, raw: Readonly<Record<string, string>>, liveVolts: number | null,
): Result<Record<string, number>, readonly string[]> {
  const out: Record<string, number> = {};
  const errors: string[] = [];
  for (const f of PHASE_FIELDS[phase]) {
    const r = parseField(f, raw[f.key] ?? "", liveVolts);
    if (!r.ok) errors.push(r.error);
    else if (r.value !== null) out[f.key] = r.value;
  }
  return errors.length > 0 ? err(errors) : ok(out);
}
