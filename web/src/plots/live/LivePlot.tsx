// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
// frob:ticket 01M6WWMS5EKF26MGK5YGR0E3TZ
import { useCallback, useEffect, useMemo, useRef } from "react";
import { getLogger } from "../../api/log";
import { isTextTarget, resolveKey } from "../../keys/keymap";
import { exportFigure, renderToCanvas } from "../core";
import { useTrace, type UseTraceOptions } from "../../hooks/useTrace";
import { buildLiveScene } from "./scene";
import { useContainerSquare } from "./useContainerSquare";

const log = getLogger("plots.live.view");

/** Save a blob through a temporary link; browser only. */
function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** Live scrolling trace: min/max envelope, event marks, saturation limits, in-plot reconnect state; F3 exports PNG. */
export function LivePlot(props: UseTraceOptions & { readonly width?: number; readonly height?: number }) {
  const { snapshot, conn, notice } = useTrace(props);
  const box = useRef<HTMLElement>(null);
  const side = useContainerSquare(box);
  const w = props.width ?? side;
  const h = props.height ?? side;
  const scene = useMemo(() => buildLiveScene(snapshot, { conn, width: w, height: h }), [snapshot, conn, w, h]);
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (ref.current) renderToCanvas(ref.current, scene);
  }, [scene]);

  const sceneRef = useRef(scene);
  sceneRef.current = scene;
  const doExport = useCallback(async () => {
    const r = await exportFigure(sceneRef.current, { format: "png", dpi: 192 });
    if (!r.ok) { log.error("export failed", { error: r.error }); return; }
    saveBlob(r.value.blob, "live-trace.png");
    log.info("exported live trace", { bytes: r.value.blob.size });
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const textFocus = isTextTarget(e.target as { tagName?: string; isContentEditable?: boolean } | null);
      if (resolveKey(e, { textFocus, nudgeActive: false }) !== "export") return;
      e.preventDefault();
      void doExport();
    };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); };
  }, [doExport]);

  return (
    <figure ref={box} data-testid="live-plot">
      <canvas ref={ref} data-testid="live-canvas" aria-label={scene.title} />
      {notice === null ? null : <p role="status" data-testid="live-notice">{notice}</p>}
      <figcaption>Press F3 to export PNG.</figcaption>
    </figure>
  );
}
