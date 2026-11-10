// frob:ticket 01M72X7ZB936PEBXHRGX06FSAD
// frob:accept COV001 because="covered by WeightPlanPanel.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useEffect, useState } from "react";
import { getJson } from "../../api/client";
import { getLogger } from "../../api/log";
import { err, ok, type Result } from "../../api/result";
import { postJson, problemText, type PostError } from "../review/api";

const log = getLogger("setup.weightPlan");
const STORE_KEY = "sadi.weightPlan.form";

/** One planned hang as the server returns it (fields used by the panel). */
export interface PlannedHang {
  readonly order: number;
  readonly weight_ids: readonly string[];
  readonly total_mass_kg: number;
  readonly u_mass_kg: number;
  readonly tension_n: number;
  readonly predicted_volts: number;
  readonly reason: string;
  readonly e_half_width_pa?: number | null;
}

/** A propagated value with its standard uncertainty. */
export interface PropQuantity { readonly name: string; readonly unit: string; readonly value: number; readonly std_unc: number; readonly low95: number; readonly high95: number }

/** Server reply of POST /api/weight-plan (fields used by the panel). */
export interface PlanReply {
  readonly plan: { readonly phase: string; readonly hangs: readonly PlannedHang[]; readonly n_usable: number; readonly dropped_capacity: number; readonly dropped_saturation: number };
  readonly cal_slope_v_per_m: number;
  readonly cal_source: string;
  readonly propagated: { readonly stress: readonly PropQuantity[]; readonly modulus?: PropQuantity | null; readonly yield_stress?: PropQuantity | null; readonly notes: readonly string[] } | null;
  readonly propagation_note: string;
}

/** Calibration default reply of GET /api/weight-plan/defaults. */
export interface CalDefaults { readonly cal_slope_v_per_m: number | null; readonly source: string; readonly explanation: string }

/** Raw form strings exactly as typed. */
export interface PlanForm {
  readonly weights: string;
  readonly unit: "g" | "kg";
  readonly diameter_mm: string;
  readonly u_diameter_mm: string;
  readonly length_mm: string;
  readonly u_length_mm: string;
  readonly slope: string;
}

/** Empty-ish starting form: 8 blank lines are not forced; lab values are typical. */
export const EMPTY_FORM: PlanForm = { weights: "", unit: "g", diameter_mm: "0.202", u_diameter_mm: "0.002", length_mm: "83.13", u_length_mm: "0.5", slope: "" };

/** Request body for POST /api/weight-plan. */
export interface PlanBody {
  readonly weights: { mass_kg: number; u_mass_kg: number }[];
  readonly diameter_m: number;
  readonly u_diameter_m: number;
  readonly length_m: number;
  readonly u_length_m: number;
  readonly cal_slope_v_per_m?: number;
}

const num = (s: string): number => (s.trim() === "" ? Number.NaN : Number(s));

/** Parse the form into a request; Err is a sentence saying what to fix. Slope blank means "use the current calibration". */
export function parsePlanForm(f: PlanForm): Result<PlanBody, string> {
  const scale = f.unit === "g" ? 1e-3 : 1;
  const lines = f.weights.split("\n").map((l) => l.trim()).filter((l) => l !== "");
  if (lines.length === 0) return err("Enter your weights, one per line (mass, then an optional uncertainty).");
  if (lines.length > 12) return err("Enter at most 12 weights.");
  const weights: { mass_kg: number; u_mass_kg: number }[] = [];
  for (const [i, l] of lines.entries()) {
    const parts = l.split(/[\s,;]+/).filter((p) => p !== "");
    const m = Number(parts[0]);
    const u = parts.length > 1 ? Number(parts[1]) : 0;
    if (parts.length > 2 || !Number.isFinite(m) || m <= 0 || !Number.isFinite(u) || u < 0) {
      return err(`Weight line ${String(i + 1)} ("${l}") should be a positive mass, then an optional uncertainty.`);
    }
    weights.push({ mass_kg: m * scale, u_mass_kg: u * scale });
  }
  const d = num(f.diameter_mm), ud = f.u_diameter_mm.trim() === "" ? 0 : num(f.u_diameter_mm);
  const l0 = num(f.length_mm), ul = f.u_length_mm.trim() === "" ? 0 : num(f.u_length_mm);
  if (!(d > 0)) return err("Wire diameter must be a positive number of millimetres.");
  if (!(l0 > 0)) return err("Gauge length L0 must be a positive number of millimetres.");
  if (!(ud >= 0) || !(ul >= 0)) return err("Uncertainties must be zero or more.");
  const body = { weights, diameter_m: d / 1000, u_diameter_m: ud / 1000, length_m: l0 / 1000, u_length_m: ul / 1000 };
  if (f.slope.trim() === "") return ok(body);
  const s = Number(f.slope);
  if (!Number.isFinite(s) || s === 0) return err("The calibration slope must be a non-zero number (volts per metre), or blank to use the current calibration.");
  return ok({ ...body, cal_slope_v_per_m: s });
}

/** Sentence with a value and its plus/minus uncertainty. */
export const pm = (v: number, u: number, digits = 4): string => `${v.toPrecision(digits)} +/- ${u.toPrecision(2)}`;

/** Presentational view of the ordered hangs and uncertainty. */
export function PlanResult({ reply }: { readonly reply: PlanReply }): React.JSX.Element {
  const hangs = reply.plan.hangs;
  const p = reply.propagated;
  return (
    <section aria-label="Planned hangs">
      <h3>Planned hangs</h3>
      <p>Hang them in this order. Calibration slope used: {reply.cal_slope_v_per_m.toPrecision(4)} V/m ({reply.cal_source === "entered" ? "entered" : "from this session's calibration"}).</p>
      <table>
        <thead><tr><th>Hang</th><th>Weights</th><th>Total (kg)</th><th>Tension (N)</th><th>Predicted (V)</th><th>Why</th></tr></thead>
        <tbody>
          {hangs.map((h) => (
            <tr key={h.order}>
              <td>#{h.order}</td>
              <td>{h.weight_ids.join(" + ")}</td>
              <td>{pm(h.total_mass_kg, h.u_mass_kg)}</td>
              <td>{h.tension_n.toPrecision(4)}</td>
              <td>{h.predicted_volts.toPrecision(4)}</td>
              <td>{h.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {reply.plan.dropped_capacity + reply.plan.dropped_saturation > 0 ? (
        <p>{String(reply.plan.dropped_capacity)} combination(s) were skipped because they would break the wire and {String(reply.plan.dropped_saturation)} because they would saturate the LVDT.</p>
      ) : null}
      {p !== null ? (
        <div aria-label="Propagated uncertainty">
          <h3>Uncertainty (95 % interval)</h3>
          {p.modulus != null ? <p>Modulus E: {pm(p.modulus.value / 1e9, p.modulus.std_unc / 1e9)} GPa (95 %: {(p.modulus.low95 / 1e9).toPrecision(4)} to {(p.modulus.high95 / 1e9).toPrecision(4)} GPa)</p> : null}
          {p.yield_stress != null ? <p>Yield stress: {pm(p.yield_stress.value / 1e6, p.yield_stress.std_unc / 1e6)} MPa</p> : null}
          <ul>{p.stress.map((q, i) => <li key={q.name}>Hang #{String(i + 1)} stress: {pm(q.value / 1e6, q.std_unc / 1e6)} MPa</li>)}</ul>
          {p.notes.map((n) => <p key={n}>{n}</p>)}
        </div>
      ) : <p>{reply.propagation_note}</p>}
    </section>
  );
}

const load = (): PlanForm => {
  try {
    const raw = typeof localStorage === "undefined" ? null : localStorage.getItem(STORE_KEY);
    return raw === null ? EMPTY_FORM : { ...EMPTY_FORM, ...(JSON.parse(raw) as Partial<PlanForm>) };
  } catch { return EMPTY_FORM; }
};

/** Weight planner: enter the weights, wire geometry and (optionally) the calibration slope; no lab or session needed. */
export function WeightPlanPanel({ fetchImpl }: { readonly fetchImpl?: typeof fetch }): React.JSX.Element {
  const [form, setForm] = useState<PlanForm>(load);
  const [defaults, setDefaults] = useState<CalDefaults | null>(null);
  const [reply, setReply] = useState<PlanReply | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void getJson<CalDefaults>("/api/weight-plan/defaults", fetchImpl).then((r) => {
      if (r.ok) setDefaults(r.value); else log.warn("defaults failed", { kind: r.error.kind });
    });
  }, [fetchImpl]);
  const set = (k: keyof PlanForm, v: string): void => { setForm((f) => ({ ...f, [k]: v }) as PlanForm); };
  const submit = (): void => {
    const parsed = parsePlanForm(form);
    if (!parsed.ok) { setMessage(parsed.error); return; }
    try { localStorage.setItem(STORE_KEY, JSON.stringify(form)); } catch { log.debug("form not persisted"); }
    setBusy(true); setMessage("Planning...");
    void postJson<PlanReply>("/api/weight-plan", parsed.value, fetchImpl).then((r) => {
      setBusy(false);
      if (r.ok) { setReply(r.value); setMessage(""); }
      else { setReply(null); setMessage(problemText(r.error as PostError, "plan the weights")); }
    });
  };
  return (
    <section aria-label="Weight plan">
      <h2>Weight plan</h2>
      <p>Enter the weights you have and the wire measurements. This needs no lab connection.</p>
      <form aria-label="Weight plan inputs" onSubmit={(e) => { e.preventDefault(); if (!busy) submit(); }}>
        <label>Weights, one per line: mass, then an optional uncertainty (same unit)<br />
          <textarea rows={8} value={form.weights} onChange={(e) => { set("weights", e.target.value); }} />
        </label>{" "}
        <label>Unit <select value={form.unit} onChange={(e) => { set("unit", e.target.value); }}><option value="g">g</option><option value="kg">kg</option></select></label>
        <p>
          <label>Wire diameter (mm) <input value={form.diameter_mm} inputMode="decimal" onChange={(e) => { set("diameter_mm", e.target.value); }} /></label>{" "}
          <label>+/- <input value={form.u_diameter_mm} inputMode="decimal" onChange={(e) => { set("u_diameter_mm", e.target.value); }} /></label>{" "}
          <label>Gauge length L0 (mm) <input value={form.length_mm} inputMode="decimal" onChange={(e) => { set("length_mm", e.target.value); }} /></label>{" "}
          <label>+/- <input value={form.u_length_mm} inputMode="decimal" onChange={(e) => { set("u_length_mm", e.target.value); }} /></label>
        </p>
        <p>
          <label>LVDT calibration slope (V per m) <input value={form.slope} inputMode="decimal" placeholder={defaults?.cal_slope_v_per_m != null ? String(defaults.cal_slope_v_per_m) : ""} onChange={(e) => { set("slope", e.target.value); }} /></label>
        </p>
        <p>{defaults?.explanation ?? ""} Leave blank to use the current calibration when there is one.</p>
        <button type="submit" disabled={busy}>Plan weights</button>
      </form>
      <p role="status">{message}</p>
      {reply !== null ? <PlanResult reply={reply} /> : null}
    </section>
  );
}
