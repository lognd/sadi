// frob:ticket 01M6W7R3EPVRGG4R93B7WJVKMW
import { useEffect, useMemo, useRef } from "react";
import { getLogger } from "../../api/log";
import { renderToCanvas } from "../core";
import { buildCreepScene } from "./scene";
import type { CreepData } from "./types";

const log = getLogger("plots.creep.view");

/** Creep figure: one strain-vs-log-time panel per hold; redraws whenever `data` changes. */
export function CreepPlot({ data }: { data: CreepData }) {
  const built = useMemo(() => buildCreepScene(data), [data]);
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (built.ok && ref.current) renderToCanvas(ref.current, built.value);
  }, [built]);
  if (!built.ok) {
    log.warn("creep plot unavailable", { kind: built.error.kind });
    return <p role="status" data-testid="creep-empty">No creep data yet.</p>;
  }
  return <canvas ref={ref} data-testid="creep-plot" aria-label={built.value.title} />;
}
