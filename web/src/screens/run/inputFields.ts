// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
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
  /** Instruction-bearing helper text shown in normal case under the field. */
  readonly help?: string;
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
  /** Not shown to the operator; filled from the live recent statistics (key mean, sd or n). */
  readonly derived?: boolean;
  /** Plausible range in the field's unit; values outside draw a warning (see plausibilityNote). */
  readonly plausible?: readonly [number, number];
  /** Belongs to the separate `specimen` point (geometry), not to the phase's own point. */
  readonly specimen?: boolean;
}

const LIVE_V: InputField = { key: "volts", label: "Volts", unit: "V", required: false, live: true };

/** Plausible wire diameter in metres (0.05 mm to 10 mm); anything else is probably a unit slip. */
const DIAMETER_RANGE_M: readonly [number, number] = [5e-5, 1e-2];

/** Plausible LVDT gauge height in metres (mirrors MAX_HEIGHT_M / MIN_HEIGHT_M in point_inputs.py). */
const HEIGHT_RANGE_M: readonly [number, number] = [0, 0.1];

/** Plausible hanging mass in kilograms (mirrors MAX_MASS_KG in point_inputs.py). */
const MASS_RANGE_KG: readonly [number, number] = [0, 20];

/** Input fields per run phase; keys match parse_inputs (calibration, tare, load). */
export const PHASE_FIELDS: Readonly<Record<RunPhase, readonly InputField[]>> = {
  calibrate: [LIVE_V, { key: "height", label: "Gauge height", unit: "m", required: true, min: 0, plausible: HEIGHT_RANGE_M }],
  tare: [
    { key: "mean", label: "Mean volts", unit: "V", required: false, live: true },
    { key: "n", label: "Sample count n", unit: "", required: false, integer: true, min: 1, derived: true },
    { key: "sd", label: "Volts sd", unit: "V", required: false, min: 0, derived: true },
    { key: "diameter", label: "Specimen diameter", unit: "m", required: true, min: 0, specimen: true, plausible: DIAMETER_RANGE_M },
    { key: "u_diameter", label: "Diameter uncertainty", unit: "m", required: false, min: 0, specimen: true },
    { key: "hanger_kg", label: "Hanger mass", unit: "kg", required: false, min: 0, specimen: true, plausible: MASS_RANGE_KG },
  ],
  elastic: [LIVE_V, { key: "mass_kg", label: "Added mass", help: "Masses added to the hanger only; the hanger is added for you.", unit: "kg", required: true, min: 0, plausible: MASS_RANGE_KG }, { key: "u_mass_kg", label: "Mass uncertainty", unit: "kg", required: false, min: 0 }],
  plastic: [LIVE_V, { key: "mass_kg", label: "Added mass", help: "Masses added to the hanger only; the hanger is added for you.", unit: "kg", required: true, min: 0, plausible: MASS_RANGE_KG }, { key: "u_mass_kg", label: "Mass uncertainty", unit: "kg", required: false, min: 0 }],
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

/** Warning for a value outside the field's plausible range, with a corrected text to offer (mm read as m); null when fine. */
export function plausibilityNote(f: InputField, raw: string): { readonly message: string; readonly suggest: string | null } | null {
  if (f.plausible === undefined) return null;
  const x = Number(raw.trim());
  if (raw.trim() === "" || !Number.isFinite(x) || x <= 0) return null;
  const [lo, hi] = f.plausible;
  if (x >= lo && x <= hi) return null;
  const mm = x / 1000;
  const small = f.unit === "kg" ? "grams" : "millimetres";
  const smallAbbr = f.unit === "kg" ? "g" : "mm";
  const fix = x > hi && mm >= lo && mm <= hi;
  return {
    message: `${f.label} ${raw.trim()} ${f.unit} looks implausible (expected ${String(lo)} to ${String(hi)} ${f.unit}).${fix ? ` Did you type ${small}? ${raw.trim()} ${smallAbbr} is ${String(mm)} ${f.unit}.` : ""}`,
    suggest: fix ? String(mm) : null,
  };
}

/** Validate all fields of a phase; Err lists every problem so none is hidden. Derived fields come from `recent`. */
export function collectInputs(
  phase: RunPhase, raw: Readonly<Record<string, string>>, liveVolts: number | null,
  recent: { readonly mean: number; readonly sd: number; readonly n: number } | null = null,
): Result<Record<string, number>, readonly string[]> {
  const out: Record<string, number> = {};
  const errors: string[] = [];
  for (const f of PHASE_FIELDS[phase]) {
    if (f.derived === true) {
      if (recent === null) errors.push(`${f.label}: not enough live readings yet; wait a moment and try again.`);
      else out[f.key] = f.key === "n" ? recent.n : recent.sd;
      continue;
    }
    const r = parseField(f, raw[f.key] ?? "", f.key === "mean" && recent !== null ? recent.mean : liveVolts);
    if (!r.ok) errors.push(r.error);
    else if (r.value !== null) out[f.key] = r.value;
  }
  return errors.length > 0 ? err(errors) : ok(out);
}

/** Split validated values into the phase point's own inputs and the specimen point's (null when no diameter). */
export function splitSpecimen(
  phase: RunPhase, values: Readonly<Record<string, number>>,
): { readonly own: Record<string, number>; readonly specimen: Record<string, number> | null } {
  const keys = new Set(PHASE_FIELDS[phase].filter((f) => f.specimen === true).map((f) => f.key));
  const own: Record<string, number> = {};
  const specimen: Record<string, number> = {};
  for (const [k, v] of Object.entries(values)) (keys.has(k) ? specimen : own)[k] = v;
  return { own, specimen: "diameter" in specimen ? specimen : null };
}
