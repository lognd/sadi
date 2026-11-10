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
  /** Design phase; "lvdt_cal" switches the wording to gauge heights. */
  readonly phase?: string;
}

/** Wording for the panel: a gauge height on the LVDT step, a weight otherwise. */
export function panelNouns(phase: string | undefined): { readonly title: string; readonly thing: string } {
  return phase === "lvdt_cal" ? { title: "Suggested next gauge height", thing: "gauge height" } : { title: "Suggested next weight", thing: "weight" };
}

/** Pure view: the suggested next weight, why, alternatives and the enough-data indicator. */
export function SuggestedWeightView(p: SuggestedWeightPanelProps): React.JSX.Element {
  const { title, thing } = panelNouns(p.phase);
  if (p.failed === true) return <section data-testid="suggested-weight"><h3>{title}</h3><p>Suggestion unavailable right now. You can still choose any {thing}.</p></section>;
  if (p.advice === null) return <section data-testid="suggested-weight"><h3>{title}</h3><p>Loading suggestion...</p></section>;
  const s = p.advice.suggestion;
  return (
    <section data-testid="suggested-weight" aria-label={title}>
      <h3>{title}</h3>
      {s !== null && (
        <>
          <p data-testid="suggested-load"><strong>{loadText(s.x, s.unit)}</strong></p>
          <p data-testid="suggested-why">{s.why}</p>
          {s.alternatives.length > 0 && <p data-testid="suggested-alts">Other good choices: {s.alternatives.map((a) => loadText(a.x, s.unit)).join(", ")}</p>}
        </>
      )}
      <p data-testid="enough-indicator">{indicatorText(p.advice.indicator)}</p>
      <p><small>This is only advice. You decide which {thing} to use.</small></p>
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
  return <SuggestedWeightView advice={advice} failed={failed} phase={p.phase} />;
}
