// frob:ticket 01M72YENT6PZMVDMYGZ2BWDNK9
// frob:accept COV001 because="covered by NextHangPanel.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useEffect, useState } from "react";
import { getJson } from "../../api/client";
import { getLogger } from "../../api/log";
import type { PlanReply, PlannedHang } from "../setup/WeightPlanPanel";

const log = getLogger("screens.run.nextHang");

/** Reply of GET /api/weight-plan/next. */
export interface NextHangReply {
  readonly captured: number;
  readonly next_hang: PlannedHang | null;
  readonly reply: PlanReply;
}

/** View state: still loading, no saved weights, unavailable, or the replanned answer. */
export type NextHangState =
  | { readonly kind: "loading" }
  | { readonly kind: "none" }
  | { readonly kind: "failed" }
  | { readonly kind: "ready"; readonly value: NextHangReply };

/** Pure view: the next planned hang (which weights to hang) after the captured points. */
export function NextHangView({ state }: { readonly state: NextHangState }): React.JSX.Element {
  const title = <h3>Next planned hang</h3>;
  if (state.kind === "loading") return <section data-testid="next-hang">{title}<p>Loading plan...</p></section>;
  if (state.kind === "none") return <section data-testid="next-hang">{title}<p>No weights saved yet. Save them from the Weight plan in Setup to see the planned hangs here.</p></section>;
  if (state.kind === "failed") return <section data-testid="next-hang">{title}<p>The weight plan is unavailable right now. You can still choose any weight.</p></section>;
  const { next_hang: h, captured, reply } = state.value;
  const left = reply.plan.hangs.length;
  return (
    <section data-testid="next-hang" aria-label="Next planned hang">
      {title}
      {h === null ? (
        <p data-testid="next-hang-done">No further hang in your plan after {String(captured)} captured point(s).</p>
      ) : (
        <>
          <p data-testid="next-hang-weights"><strong>Hang {h.weight_ids.join(" + ")}</strong> ({h.total_mass_kg.toPrecision(4)} kg, expect about {h.predicted_volts.toPrecision(4)} V)</p>
          <p data-testid="next-hang-why">{h.reason}</p>
          <p><small>{String(left)} hang(s) remain, replanned from {String(captured)} captured point(s). This is only a plan; you decide.</small></p>
        </>
      )}
    </section>
  );
}

/** Fetches the replanned next hang and refetches whenever `tick` changes (after each captured point). */
export function NextHangPanel(p: { readonly tick: number; readonly fetchImpl?: typeof fetch }): React.JSX.Element {
  const [state, setState] = useState<NextHangState>({ kind: "loading" });
  useEffect(() => {
    let alive = true;
    void getJson<NextHangReply>("/api/weight-plan/next", p.fetchImpl).then((r) => {
      if (!alive) return;
      if (r.ok) setState({ kind: "ready", value: r.value });
      else if (r.error.kind === "http" && r.error.status === 404) setState({ kind: "none" });
      else { log.warn("next hang unavailable"); setState({ kind: "failed" }); }
    });
    return () => { alive = false; };
  }, [p.tick, p.fetchImpl]);
  return <NextHangView state={state} />;
}
