// frob:ticket 01M6W7RAPKVH796SZ6Z9EFDXQE
import { useState, type KeyboardEvent } from "react";
import { getLogger } from "../../api/log";
import type { GuidancePhase, GuidanceState } from "./types";

const log = getLogger("components.guidance");

/** Key that accepts the proposed phase change (advisory; the user may ignore it). */
export const ADVANCE_KEY = "n";

/** Next-step text; names the suggested load when the server proposes one. */
export function nextStepText(g: GuidanceState): string {
  if (g.suggested_load_kg === null) return g.next_action;
  return `${g.next_action} (${g.suggested_load_kg.toFixed(3)} kg)`;
}

/** Expected value line (e.g. "Expected E: 70 GPa"), or null when unknown. */
export function expectedText(g: GuidanceState): string | null {
  if (g.expected_value === null) return null;
  return `Expected ${g.confidence.quantity}: ${String(g.expected_value)}${g.unit ? ` ${g.unit}` : ""}`;
}

/** Meter value as a whole percent in [0, 100]. */
export function meterPercent(g: GuidanceState): number {
  return Math.round(Math.min(1, Math.max(0, g.confidence.fraction)) * 100);
}

/** Parse the inline target (percent text, e.g. "5") to a fraction; null when invalid. */
export function parseTargetPercent(text: string): number | null {
  const v = Number(text.trim());
  return Number.isFinite(v) && v > 0 && v <= 100 ? v / 100 : null;
}

/** Label for the proposal, e.g. "Move to elastic phase" or "Finish run". */
export function advanceLabel(next: GuidancePhase | null): string {
  return next === null ? "Finish run" : `Move to ${next} phase`;
}

/** Confidence meter with aria value attributes. */
export function ConfidenceMeter({ g }: { g: GuidanceState }) {
  const pct = meterPercent(g);
  const c = g.confidence;
  const rel = c.relative === null ? "no estimate yet" : `${(c.relative * 100).toFixed(1)} % half-width`;
  return (
    <div>
      <div role="meter" aria-label={`Confidence in ${c.quantity}`} aria-valuemin={0} aria-valuemax={100}
           aria-valuenow={pct} aria-valuetext={`${String(pct)} percent of target (${rel})`}
           data-testid="confidence-meter" data-met={String(c.met)}>
        <div className="meter-fill" style={{ width: `${String(pct)}%` }} />
      </div>
      <span>{c.met ? "Confidence is enough" : `${String(pct)} % of the way to the target (${rel})`}</span>
    </div>
  );
}

/** Advisory stop-early banner; the button or the key calls onAdvance, nothing advances on its own. */
export function StopEarlyBanner(props: { g: GuidanceState; onAdvance?: () => void }) {
  const { g, onAdvance } = props;
  if (!g.stop_early && !g.run_complete_proposed) return null;
  return (
    <div role="status" data-testid="stop-early">
      <p>{`Suggestion: ${g.stop_reason} You may keep going.`}</p>
      {onAdvance ? (
        <button type="button" aria-keyshortcuts={ADVANCE_KEY.toUpperCase()} onClick={() => {
          log.info("advance accepted by click", { next: g.proposed_next_phase });
          onAdvance();
        }}>
          {`${advanceLabel(g.proposed_next_phase)} (${ADVANCE_KEY.toUpperCase()})`}
        </button>
      ) : null}
    </div>
  );
}

/** Key handler: calls onAdvance only for the advance key while a proposal is showing. */
export function handleAdvanceKey(
  e: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey">,
  g: GuidanceState,
  onAdvance?: () => void,
): boolean {
  if (!onAdvance || !(g.stop_early || g.run_complete_proposed)) return false;
  if (e.ctrlKey || e.metaKey || e.altKey || e.key.toLowerCase() !== ADVANCE_KEY) return false;
  log.info("advance accepted by key", { next: g.proposed_next_phase });
  onAdvance();
  return true;
}

/** Guidance panel: next step, confidence meter with editable target, advisory stop-early banner. */
export function GuidancePanel(props: {
  guidance: GuidanceState | null;
  /** Current target as a fraction (default 0.05). */
  target?: number;
  onTargetChange?: (fraction: number) => void;
  onAdvance?: () => void;
}) {
  const { guidance: g, target = 0.05, onTargetChange, onAdvance } = props;
  const [text, setText] = useState(String(+(target * 100).toFixed(2)));
  const [bad, setBad] = useState(false);
  if (g === null) {
    return <section aria-label="Guidance"><p>No guidance yet.</p></section>;
  }
  const commit = (): void => {
    const f = parseTargetPercent(text);
    if (f === null) {
      log.warn("invalid target rejected", { text });
      setBad(true);
      return;
    }
    setBad(false);
    log.info("target changed", { fraction: f });
    onTargetChange?.(f);
  };
  const expected = expectedText(g);
  return (
    <section aria-label="Guidance" tabIndex={-1} onKeyDown={(e) => { handleAdvanceKey(e, g, onAdvance); }}>
      <p data-testid="next-step">{nextStepText(g)}</p>
      {expected ? <p data-testid="expected">{expected}</p> : null}
      <p>{`Point ${String(g.points_taken)} of ${String(g.max_points)} (${g.phase})`}</p>
      <ConfidenceMeter g={g} />
      <label>
        {"Target half-width (%) "}
        <input type="text" inputMode="decimal" value={text} aria-invalid={bad}
               onChange={(e) => { setText(e.target.value); }} onBlur={commit}
               onKeyDown={(e) => { e.stopPropagation(); if (e.key === "Enter") commit(); }} />
      </label>
      {bad ? <p role="alert">Enter a percentage above 0 and at most 100.</p> : null}
      <StopEarlyBanner g={g} onAdvance={onAdvance} />
    </section>
  );
}
