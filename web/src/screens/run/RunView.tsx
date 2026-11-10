// frob:ticket 01M6X9NXTD91A49K5KE81EQRYA
// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
import { CalibrationPlot } from "../../plots/calibration";
import type { CalibrationData } from "../../plots/calibration";
import { StressStrainScreen } from "../StressStrainScreen";
import type { StressStrainData } from "../../plots/stressstrain";
import type { LiveView } from "./live";
export { settleText } from "../../components/live/settle";
import { PHASE_FIELDS, plausibilityNote } from "./inputFields";
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

/** Presentational run screen body (live readout and trace live in the front panel): phase plot, saturation warning, capture and confirmation. */
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
      <fieldset aria-label="Capture inputs" aria-describedby="hotkey-hint">
        <legend>Capture inputs (SI units)</legend>
        {PHASE_FIELDS[p.phase].filter((f) => f.derived !== true).map((f) => {
          const note = plausibilityNote(f, p.fields[f.key] ?? "");
          return (
            <span key={f.key}>
              <label className="field">
                {f.label}{f.unit ? ` (${f.unit})` : ""}{f.required ? " *" : ""}{" "}
                <input
                  type="text" inputMode="decimal" name={f.key} value={p.fields[f.key] ?? ""}
                  placeholder={f.live === true ? (v.volts === null ? "live" : `live ${v.volts.toFixed(4)}`) : ""}
                  onChange={(e) => { p.onField(f.key, e.target.value); }}
                />
              </label>
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
      <small data-testid="hotkey-hint" id="hotkey-hint" role="note"> {TEXT_FIELD_HOTKEY_HINT}</small>
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
