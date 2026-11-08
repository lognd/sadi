// frob:ticket 01M6W7R3KN3HXVMJQ1D3MJNBZY
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import { getLogger } from "../../api/log";
import { computeLayout, renderToCanvas } from "../core";
import { buildStressStrainScene } from "./buildScene";
import type { Edge } from "./selection";
import { dragWindow, keyStep, setEdge } from "./selection";
import type { FitWindow, StressStrainData } from "./model";

const log = getLogger("plots.stressstrain.component");

/** Props: data to draw and a callback fired when the user commits a new window (triggers the API refit). */
export interface StressStrainPlotProps {
  readonly data: StressStrainData;
  readonly onWindowChange: (w: FitWindow) => void;
}

/** Canvas stress-strain plot with a draggable and keyboard-adjustable fit window. */
export function StressStrainPlot({ data, onWindowChange }: StressStrainPlotProps): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const drag = useRef<Edge | null>(null);
  const scene = useMemo(() => buildStressStrainScene(data), [data]);
  const n = data.points.length;
  const win: FitWindow | null = data.fit === null ? null : { first: data.fit.first, last: data.fit.last };
  const [focus, setFocus] = useState<Edge>("first");

  useEffect(() => {
    if (canvas.current !== null) renderToCanvas(canvas.current, scene);
  }, [scene]);

  const emit = useCallback((w: FitWindow | null) => {
    if (w === null || win === null || (w.first === win.first && w.last === win.last)) return;
    log.info("window changed", { window: w });
    onWindowChange(w);
  }, [onWindowChange, win]);

  const strainAt = (e: PointerEvent<HTMLCanvasElement>): number => {
    const r = e.currentTarget.getBoundingClientRect();
    const layout = computeLayout(scene);
    const px = ((e.clientX - r.left) / r.width) * scene.width;
    const m = layout.xMap;
    return m.d0 + ((px - m.r0) / (m.r1 - m.r0)) * (m.d1 - m.d0);
  };
  const strains = useMemo(() => data.points.map((p) => p.strain), [data.points]);

  const onDown = (e: PointerEvent<HTMLCanvasElement>): void => {
    if (win === null) return;
    const r = dragWindow(strains, win, strainAt(e));
    if (r === null) return;
    drag.current = r.edge;
    setFocus(r.edge);
    e.currentTarget.setPointerCapture(e.pointerId);
    emit(r.window);
  };
  const onMove = (e: PointerEvent<HTMLCanvasElement>): void => {
    if (win === null || drag.current === null) return;
    const r = dragWindow(strains, win, strainAt(e), drag.current);
    if (r !== null) emit(r.window);
  };
  const onUp = (): void => { drag.current = null; };

  const onKey = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (win === null) return;
    if (e.key === "Tab") return;
    const edge: Edge = e.key === "[" ? "first" : e.key === "]" ? "last" : focus;
    if (e.key === "[" || e.key === "]") { setFocus(edge); e.preventDefault(); return; }
    const next = keyStep(win, edge, e.key, e.shiftKey, n);
    if (next !== null) { e.preventDefault(); emit(next); }
  };

  return (
    <div
      role="group"
      aria-label="Stress-strain plot with fit window"
      tabIndex={0}
      onKeyDown={onKey}
      data-testid="stress-strain-plot"
    >
      <canvas
        ref={canvas}
        aria-label="Stress-strain curve"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
      />
      {win !== null && (
        <p>
          <label>
            Window start
            <input
              type="range" min={0} max={n - 1} value={win.first}
              onFocus={() => { setFocus("first"); }}
              onChange={(e) => { emit(setEdge(win, "first", Number(e.target.value), n)); }}
            />
          </label>
          <label>
            Window end
            <input
              type="range" min={0} max={n - 1} value={win.last}
              onFocus={() => { setFocus("last"); }}
              onChange={(e) => { emit(setEdge(win, "last", Number(e.target.value), n)); }}
            />
          </label>
          <span aria-live="polite">Fit window: points {win.first} to {win.last}. Arrows move the {focus} edge; [ and ] switch edge.</span>
        </p>
      )}
    </div>
  );
}
