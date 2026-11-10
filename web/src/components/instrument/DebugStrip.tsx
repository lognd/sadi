// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
// frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5
// frob:ticket 01M727TR8PNCVA3CA5ZAVFBREF
// frob:accept COV001 because="covered by instrument.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useEffect, useState } from "react";
import { useLive } from "../../state/LiveContext";
import type { FrameMeta } from "../../hooks/useTrace";
import type { BackendFacts } from "./useBackendFacts";

/** Frame age (ms) above which the stream counts as stale. */
export const STALE_FRAME_MS = 1500;

/** Text for a field the backend does not expose: always says why. */
export function unavailable(reason: string): string { return `unavailable (${reason})`; }

/** Frame age text and state from the newest frame time. */
export function frameAge(meta: FrameMeta | null | undefined, nowMs: number): { text: string; state: "ok" | "stale" | "none" } {
  if (meta == null) return { text: "no frames yet", state: "none" };
  const ms = Math.max(0, nowMs - meta.atMs);
  return { text: `${String(Math.round(ms))} ms`, state: ms > STALE_FRAME_MS ? "stale" : "ok" };
}

/** Device row text: a fault (error status, device fault or acquisition fault) renders as "(!) fault: reason", never "[ok]". */
export function deviceText(d: NonNullable<BackendFacts["device"]>): string {
  const reason = d.fault ?? d.acquisitionFault;
  if (d.status === "error" || reason !== null) return `(!) fault: ${reason ?? (d.hint || d.status)}`;
  return `${d.attached || d.status === "simulated" ? "[ok]" : "(!)"} ${d.status}`;
}

/** Presentational debug strip: every field always visible; missing ones say why. */
export function DebugStripView({ meta, nowMs, facts, backend }: { readonly meta: FrameMeta | null | undefined; readonly nowMs: number; readonly facts: BackendFacts; readonly backend: string }): React.JSX.Element {
  const age = frameAge(meta, nowMs);
  const rate = meta == null || meta.dtS <= 0 ? "--" : `${(1 / meta.dtS).toFixed(0)} Hz`;
  const save = facts.save === null ? unavailable("save status not reachable") : `${facts.save.state === "saved" ? "[ok]" : "(!)"} ${facts.save.label || facts.save.state}${facts.save.pending > 0 ? ` (${String(facts.save.pending)} pending)` : ""}`;
  const device = facts.device === null ? unavailable("device status not reachable") : deviceText(facts.device);
  const rows: readonly (readonly [string, string, string?])[] = [
    ["Device", device],
    ["Firmware", unavailable("backend does not report firmware yet")],
    ["Sample rate", rate],
    // Two different seq spaces, labelled apart: WS frame seq (hub-assigned) vs WAL raw seq (durable / queued).
    ["WS frame seq", meta == null ? "--" : String(meta.seq)],
    ["WAL seq (durable / queued)", meta == null ? "--" : `${String(meta.durableSeq)} / ${String(meta.enqueuedSeq)}`],
    ["Frame age", `${age.state === "stale" ? "(!) " : ""}${age.text}`, age.state],
    ["Backend", backend],
    ["Session", facts.session === null ? "none open" : facts.session.name],
    ["Data folder", facts.dataRoot !== null ? facts.dataRoot : unavailable("backend does not report the active folder")],
    ["Save / WAL", save],
    ["Last error", facts.lastError === null ? "none" : `(!) ${facts.lastError}`],
  ];
  return (
    <section className="debug-strip" aria-label="Debug">
      <dl className="ds-grid">
        {rows.map(([k, v, st]) => <div key={k} data-state={st}><dt>{k}</dt><dd>{v}</dd></div>)}
      </dl>
    </section>
  );
}

/** Always-visible debug strip: ticks once a second so frame age stays current. */
export function DebugStrip({ backend, facts }: { readonly backend: string; readonly facts: BackendFacts }): React.JSX.Element {
  const { meta } = useLive();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = setInterval(() => { setNow(Date.now()); }, 500); return () => { clearInterval(id); }; }, []);
  return <DebugStripView meta={meta} nowMs={now} facts={facts} backend={backend} />;
}
