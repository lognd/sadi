// frob:ticket 01M6X9NXTD91A49K5KE81EQRYA
// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
import { CalibrationPlot } from "../../plots/calibration";
import type { CalibrationData } from "../../plots/calibration";
import { StressStrainScreen } from "../StressStrainScreen";
import type { StressStrainData } from "../../plots/stressstrain";
import type { LiveView } from "./live";
import { PHASE_FIELDS } from "./inputFields";
import { PHASES, type RunPhase } from "./phases";

/** Per-phase live plot payload supplied by the host (see docs/web/run-screens.md gap G2). */
export type PhasePlot =
  | { readonly kind: "calibration"; readonly data: CalibrationData }
  | { readonly kind: "stress-strain"; readonly data: StressStrainData };

/** Props of the presentational run view. */
export interface RunViewProps {
  readonly phase: RunPhase;
  readonly view: LiveView;
  /** Live trace element (LivePlot in production, a stub in tests). */
  readonly trace: React.ReactNode;
  readonly plot: PhasePlot | null;
  /** Reason capture is blocked right now, or null. */
  readonly blockedWhy: string | null;
  /** True while the forced-early confirmation is open. */
  readonly confirming: boolean;
  readonly message: string | null;
  /** Raw text of each input field, by key. */
  readonly fields: Readonly<Record<string, string>>;
  readonly onField: (key: string, value: string) => void;
  readonly onAccept: () => void;
  /** Operator confirms a load was applied (marks a load change on the live run). */
  readonly onLoadChange: () => void;
  readonly onConfirmEarly: () => void;
  readonly onCancelEarly: () => void;
}

/** Text for the creep/settle indicator, with drift rate when known. */
export function settleText(v: LiveView): string {
  if (v.motion === "settled") return "[Settled]";
  if (v.motion === "unknown") return "[Measuring...]";
  return v.driftVps === null ? "[Creeping]" : `[Creeping ${Math.abs(v.driftVps * 1000).toFixed(1)} mV/s]`;
}

/** Presentational run screen body: readouts, trace, phase plot, saturation warning, capture and confirmation. */
export function RunView(p: RunViewProps): React.JSX.Element {
  const meta = PHASES[p.phase];
  const v = p.view;
  return (
    <section aria-label={meta.title}>
      <h2>{meta.title}</h2>
      <p>{meta.instruction}</p>
      {v.signal === "saturated" && (
        <p role="alert" data-testid="saturation-warning">
          (!) The reading is at its limit (saturated). Lower the load, then try again.
        </p>
      )}
      {v.source === "disconnected" && (
        <p role="alert" data-testid="disconnect-notice">
          (!) Disconnected from the instrument. Reconnecting automatically; data already saved is untouched and capture is paused.
        </p>
      )}
      <p data-testid="readout" style={{ fontSize: "2.5rem" }} aria-live="off">
        Live V: {v.volts === null ? "--" : v.volts.toFixed(4)} V {settleText(v)}{v.stale ? " (stale)" : ""}
      </p>
      {p.trace}
      <fieldset aria-label="Capture inputs">
        <legend>Capture inputs (SI units)</legend>
        {PHASE_FIELDS[p.phase].map((f) => (
          <label key={f.key} style={{ display: "inline-block", marginRight: "1rem" }}>
            {f.label}{f.unit ? ` (${f.unit})` : ""}{f.required ? " *" : ""}{" "}
            <input
              type="text" inputMode="decimal" name={f.key} value={p.fields[f.key] ?? ""}
              placeholder={f.live === true ? (v.volts === null ? "live" : `live ${v.volts.toFixed(4)}`) : ""}
              onChange={(e) => { p.onField(f.key, e.target.value); }}
            />
          </label>
        ))}
      </fieldset>
      {p.plot?.kind === "calibration" && <CalibrationPlot data={p.plot.data} />}
      {p.plot?.kind === "stress-strain" && <StressStrainScreen key={p.plot.data.points.length} initial={p.plot.data} />}
      {p.confirming ? (
        <div role="alertdialog" aria-label="Accept early" data-testid="confirm-early">
          <p>The reading has not settled. Accept anyway? It will be recorded as unsettled.</p>
          <button type="button" onClick={p.onConfirmEarly}>Accept anyway (Shift+Space)</button>{" "}
          <button type="button" onClick={p.onCancelEarly}>Cancel (Esc)</button>
        </div>
      ) : (
        <button type="button" onClick={p.onAccept} disabled={p.blockedWhy !== null}>{meta.acceptLabel} (Space)</button>
      )}
      {" "}<button type="button" onClick={p.onLoadChange}>Mark load change</button>
      <small data-testid="load-change-hint"> Press this after applying a load; Settled cannot show until you do.</small>
      {p.blockedWhy !== null && <p data-testid="blocked-why">{p.blockedWhy}</p>}
      {p.message !== null && <p role="status" data-testid="run-message">{p.message}</p>}
    </section>
  );
}
