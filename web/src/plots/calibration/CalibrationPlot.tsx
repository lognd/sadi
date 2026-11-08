// frob:ticket 01M6W7R3D3KT3NM6JETDDAPA9P
import { useEffect, useMemo, useRef } from "react";
import { getLogger } from "../../api/log";
import { renderToCanvas, type Scene } from "../core";
import { buildCalibrationScenes } from "./scenes";
import type { CalibrationData } from "./types";

const log = getLogger("plots.calibration.view");

function Panel({ scene, testId }: { scene: Scene; testId: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (ref.current) renderToCanvas(ref.current, scene);
  }, [scene]);
  return <canvas ref={ref} data-testid={testId} aria-label={scene.title} />;
}

/** Calibration figure: fit plot over a linked residual strip; redraws whenever `data` changes. */
export function CalibrationPlot({ data }: { data: CalibrationData }) {
  const built = useMemo(() => buildCalibrationScenes(data), [data]);
  if (!built.ok) {
    log.warn("calibration plot unavailable", { kind: built.error.kind });
    return <p role="status" data-testid="calibration-empty">No calibration fit yet.</p>;
  }
  return (
    <figure data-testid="calibration-plot">
      <Panel scene={built.value.main} testId="calibration-main" />
      <Panel scene={built.value.residuals} testId="calibration-residuals" />
    </figure>
  );
}
