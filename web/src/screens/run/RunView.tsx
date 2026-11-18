// frob:ticket 01M6X9NXTD91A49K5KE81EQRYA
// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
// frob:ticket 01M7274EKWS410XEGZGFD6HWHK
// frob:ticket 01M72YKF3EN8RJX7RCH78JDPQC
import { CalibrationPlot } from "../../plots/calibration";
import type { CalibrationData } from "../../plots/calibration";
import { StressStrainScreen } from "../StressStrainScreen";
import type { StressStrainData } from "../../plots/stressstrain";
import type { LiveView } from "./live";
export { settleText } from "../../components/live/settle";
import { PHASE_FIELDS, plausibilityNote } from "./inputFields";
import { RepeatedReadingsPanel } from "./RepeatedReadingsPanel";
import { PHASES, type RunPhase } from "./phases";
import { TEXT_FIELD_HOTKEY_HINT } from "../../keys/keymap";

/** Per-phase live plot payload supplied by the host (see docs/web/run-screens.md gap G2). */
export type PhasePlot =
  | { readonly kind: "calibration"; readonly data: CalibrationData }
  | { readonly kind: "stress-strain"; readonly data: StressStrainData };

/** Props of the presentational run view. */
export interface RunViewProps {
  readonly phase: RunPhase;
  readonly view: LiveView;
  /** Accepted points so far for this step, or null while unknown. */
  readonly pointCount?: number | null;
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

/** Per-phase live plot (calibration line or stress-strain); rendered below the Finish button, after the capture card. */
export function RunPlot({ plot }: { readonly plot: PhasePlot | null }): React.JSX.Element | null {
  if (plot === null) return null;
  return plot.kind === "calibration"
    ? <CalibrationPlot data={plot.data} />
    : <StressStrainScreen key={plot.data.points.length} initial={plot.data} />;
}

/** Presentational capture card (directly under Do this, above Finish): instructions, alerts, inputs, Accept point and the phase-specific mark button. */
export function RunView(p: RunViewProps): React.JSX.Element {
  const meta = PHASES[p.phase];
  const v = p.view;
  return (
    <section aria-label={meta.title} className="capture-card" data-testid="capture-card">
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
      {v.source === "faulted" && (
        <p role="alert" data-testid="fault-notice">
          (!) The instrument faulted. It is not connected; data already saved is untouched. Check the device connection.
        </p>
      )}
      <fieldset aria-label="Capture inputs" aria-describedby="hotkey-hint">
        <legend>Capture inputs (SI units)</legend>
        {PHASE_FIELDS[p.phase].filter((f) => f.derived !== true).map((f) => {
          const note = plausibilityNote(f, p.fields[f.key] ?? "");
          return (
            <span key={f.key}>
              <label className="field" data-long={f.help !== undefined || f.label.split(/\s+/).length > 3 ? "true" : undefined}>
                {f.label}{f.unit ? ` (${f.unit})` : ""}{f.required ? " *" : ""}{" "}
                <input
                  type="text" inputMode="decimal" name={f.key} value={p.fields[f.key] ?? ""}
                  placeholder={f.live === true ? (v.volts === null ? "live" : `live ${v.volts.toFixed(4)}`) : ""}
                  onChange={(e) => { p.onField(f.key, e.target.value); }}
                />
              </label>
              {f.help !== undefined && <small className="field-help" data-testid={`help-${f.key}`}> {f.help}</small>}
              {note !== null && (
                <span role="alert" data-testid={`plausible-${f.key}`}>
                  {" "}(!) {note.message}
                  {note.suggest !== null && <>{" "}<button type="button" onClick={() => { p.onField(f.key, note.suggest ?? ""); }}>Use {note.suggest} {f.unit}</button></>}
                </span>
              )}
            </span>
          );
        })}
      </fieldset>
      {p.phase === "tare" && (
        <RepeatedReadingsPanel
          label="specimen diameter" unit="m"
          onUse={(mean, u95) => { p.onField("diameter", String(mean)); p.onField("u_diameter", String(u95)); }}
        />
      )}
      <small data-testid="hotkey-hint" id="hotkey-hint" role="note"> {TEXT_FIELD_HOTKEY_HINT}</small>
      {p.confirming ? (
        <div role="alertdialog" aria-label="Accept early" data-testid="confirm-early">
          <p>The reading has not settled. Accept anyway? It will be recorded as unsettled.</p>
          <button type="button" onClick={p.onConfirmEarly}>Accept anyway (Shift+Space)</button>{" "}
          <button type="button" onClick={p.onCancelEarly}>Cancel (Esc)</button>
        </div>
      ) : (
        <button type="button" onClick={p.onAccept} disabled={p.blockedWhy !== null}>{meta.acceptLabel} (Space)</button>
      )}
      {" "}<button type="button" onClick={p.onLoadChange} data-testid="mark-load-change">{meta.markLabel}</button>
      <small data-testid="load-change-hint"> {meta.markHint}</small>
      {p.pointCount != null && (
        <p data-testid="point-count">Accepted points: {p.pointCount} (at least {meta.minPoints} needed before you can finish).</p>
      )}
      {p.blockedWhy !== null && <p data-testid="blocked-why">{p.blockedWhy}</p>}
      {p.message !== null && <p role="status" data-testid="run-message">{p.message}</p>}
    </section>
  );
}
