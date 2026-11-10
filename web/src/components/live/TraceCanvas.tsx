// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:accept COV001 because="covered by LiveReadout.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { SyntheticBanner } from "../provenance/SyntheticBanner";
import { useEffect, useMemo, useRef } from "react";
import { renderToCanvas } from "../../plots/core";
import { buildLiveScene, useContainerSquare, type Snapshot } from "../../plots/live";
import { useLive } from "../../state/LiveContext";
import type { ConnState } from "../../ws/client";

/** Canvas drawing the shared live scene from a snapshot (no second socket). */
export function TraceCanvas({ snapshot, conn }: { readonly snapshot: Snapshot; readonly conn: ConnState }): React.JSX.Element {
  const box = useRef<HTMLDivElement>(null);
  const side = useContainerSquare(box);
  const scene = useMemo(() => buildLiveScene(snapshot, { conn, width: side, height: side }), [snapshot, conn, side]);
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => { if (ref.current) renderToCanvas(ref.current, scene); }, [scene]);
  return <div ref={box} className="live-trace-box"><canvas ref={ref} data-testid="live-canvas" aria-label={scene.title} /></div>;
}

/** Persistent live trace card fed from the shared LiveProvider. */
export function LiveTrace(): React.JSX.Element {
  const { snapshot, conn, notice } = useLive();
  return (
    <section className="card live-trace" aria-label="Live trace">
      <h2>Live trace</h2>
      <SyntheticBanner compact />
      <TraceCanvas snapshot={snapshot} conn={conn} />
      {notice === null ? null : <p role="status" data-testid="live-notice">{notice}</p>}
    </section>
  );
}
