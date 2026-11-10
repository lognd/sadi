// frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
// frob:accept COV001 because="covered by SuggestedWeightPanel.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useEffect, useState } from "react";
import { getLogger } from "../../api/log";
import { getDesignAdvice, indicatorText, loadText, type DesignAdvice } from "./designAdvice";

const log = getLogger("screens.run.suggestedWeight");

/** Props of the suggested-weight panel. */
export interface SuggestedWeightPanelProps {
  readonly advice: DesignAdvice | null;
  readonly failed?: boolean;
}

/** Pure view: the suggested next weight, why, alternatives and the enough-data indicator. */
export function SuggestedWeightView(p: SuggestedWeightPanelProps): React.JSX.Element {
  if (p.failed === true) return <section data-testid="suggested-weight"><h3>Suggested next weight</h3><p>Suggestion unavailable right now. You can still choose any weight.</p></section>;
  if (p.advice === null) return <section data-testid="suggested-weight"><h3>Suggested next weight</h3><p>Loading suggestion...</p></section>;
  const s = p.advice.suggestion;
  return (
    <section data-testid="suggested-weight" aria-label="Suggested next weight">
      <h3>Suggested next weight</h3>
      {s !== null && (
        <>
          <p data-testid="suggested-load"><strong>{loadText(s.x, s.unit)}</strong></p>
          <p data-testid="suggested-why">{s.why}</p>
          {s.alternatives.length > 0 && <p data-testid="suggested-alts">Other good choices: {s.alternatives.map((a) => loadText(a.x, s.unit)).join(", ")}</p>}
        </>
      )}
      <p data-testid="enough-indicator">{indicatorText(p.advice.indicator)}</p>
      <p><small>This is only advice. You decide which weight to add.</small></p>
    </section>
  );
}

/** Fetches the advice for `phase` and refetches whenever `tick` changes (after each captured point). */
export function SuggestedWeightPanel(p: { readonly phase: string; readonly tick: number; readonly fetchImpl?: typeof fetch }): React.JSX.Element {
  const [advice, setAdvice] = useState<DesignAdvice | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    void getDesignAdvice(p.phase, p.fetchImpl).then((r) => {
      if (!alive) return;
      if (r.ok) { setAdvice(r.value); setFailed(false); }
      else { log.warn("design advice unavailable"); setFailed(true); }
    });
    return () => { alive = false; };
  }, [p.phase, p.tick, p.fetchImpl]);
  return <SuggestedWeightView advice={advice} failed={failed} />;
}
