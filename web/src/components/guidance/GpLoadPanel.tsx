// frob:ticket 01M71KE93DMK963M32SPH83NF4
// frob:accept COV001 because="covered by GpLoadPanel.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { getLogger } from "../../api/log";
import type { GuidanceState } from "./types";

const log = getLogger("components.guidance.gp");

/** Standard gravity (m/s^2) used to show a load in newtons. */
export const STANDARD_GRAVITY = 9.80665;

/** Maximum number of alternative loads offered as fill buttons. */
export const MAX_ALTERNATIVES = 3;

/** Convert a mass load in kg to newtons. */
export function kgToNewtons(kg: number): number {
  return kg * STANDARD_GRAVITY;
}

/** Format a load as "1.250 kg (12.26 N)". */
export function loadText(kg: number): string {
  return `${kg.toFixed(3)} kg (${kgToNewtons(kg).toFixed(2)} N)`;
}

/** True when the server sent GP fields (a non-empty gp_state); false means even-schedule fallback. */
export function hasGp(g: GuidanceState): boolean {
  return (g.gp_state ?? "") !== "";
}

/** Alternatives capped to MAX_ALTERNATIVES, finite values only. */
export function alternativesOf(g: GuidanceState): number[] {
  return (g.alternatives ?? []).filter((v) => Number.isFinite(v)).slice(0, MAX_ALTERNATIVES);
}

/** Advisory sentence for a GP state; never blocks anything. */
export function gpStateNote(state: string): string {
  switch (state) {
    case "collecting": return "Collecting points: the model needs a few more before it can advise.";
    case "enough": return "Stop early is reasonable: more points are unlikely to help.";
    case "diminishing": return "Diminishing returns: further points add little. You may stop early.";
    case "unreliable": return "Model looks unreliable; showing a safe even-schedule load instead.";
    default: return "";
  }
}

/** Panel for the GP-recommended next load, gain, confidence, alternatives and stop-early hint. */
export function GpLoadPanel(props: {
  guidance: GuidanceState;
  /** Called with a load in kg when the user clicks the recommendation or an alternative. */
  onPickLoad?: (kg: number) => void;
}) {
  const { guidance: g, onPickLoad } = props;
  const load = g.suggested_load_kg;
  if (!hasGp(g)) {
    return (
      <section aria-label="Recommended load" data-testid="gp-fallback">
        <p>
          {load === null
            ? "No load suggestion yet."
            : `Even-schedule suggestion: ${loadText(load)}. The GP model is not active.`}
        </p>
      </section>
    );
  }
  const alts = alternativesOf(g);
  const note = gpStateNote(g.gp_state ?? "");
  const pick = (kg: number): void => {
    log.info("load picked", { kg });
    onPickLoad?.(kg);
  };
  return (
    <section aria-label="Recommended load" data-testid="gp-panel" data-gp-state={g.gp_state}>
      {load === null ? <p>No load suggestion yet.</p> : (
        <p data-testid="gp-load" style={{ fontVariantNumeric: "tabular-nums" }}>
          {"Recommended next load: "}<strong>{loadText(load)}</strong>
        </p>
      )}
      <dl style={{ fontVariantNumeric: "tabular-nums" }}>
        <dt>Expected gain</dt>
        <dd data-testid="gp-gain">
          {g.expected_gain == null ? "n/a" : `${(g.expected_gain * 100).toFixed(1)} % narrower`}
        </dd>
        <dt>Expected half-width after</dt>
        <dd data-testid="gp-half-width">
          {g.expected_half_width == null ? "n/a" : `${g.expected_half_width.toPrecision(3)} ${g.unit}`.trim()}
        </dd>
      </dl>
      {alts.length > 0 ? (
        <div role="group" aria-label="Alternative loads" data-testid="gp-alternatives">
          {alts.map((kg) => (
            <button key={kg} type="button" aria-label={`Use alternative load ${loadText(kg)}`}
                    onClick={() => { pick(kg); }} style={{ fontVariantNumeric: "tabular-nums" }}>
              {`${kg.toFixed(3)} kg`}
            </button>
          ))}
        </div>
      ) : null}
      {note ? <p role="status" data-testid="gp-note">{note}</p> : null}
    </section>
  );
}
