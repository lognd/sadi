// frob:ticket 01M6WM4ZDY9EHM2BW9312B5SEY
import { err, ok } from "../../api/result";
import type { Result } from "../../api/result";
import { getLogger } from "../../api/log";
import type { Theme } from "../theme";
import { buildDrawList } from "./drawlist";
import type { DrawOp } from "./drawlist";
import { computeLayout, resolveAxis } from "./layout";
import type { AnnotationBox, AxisSpec, Band, Column, FitLine, PointLabel, PointMarker, Scene, Series, Span } from "./scene";

const log = getLogger("plots.figure");

/** Why a plot cannot be drawn; returned instead of throwing so callers can show it. */
export type PlotError =
  | { readonly kind: "non_positive"; readonly axis: "x" | "y"; readonly source: string; readonly index: number; readonly value: number }
  | { readonly kind: "bad_bounds"; readonly axis: "x" | "y"; readonly detail: string }
  | { readonly kind: "no_panels" };

/** Human-readable one-line description of a PlotError. */
export function describePlotError(e: PlotError): string {
  switch (e.kind) {
    case "non_positive":
      return `log ${e.axis} axis needs positive data: ${e.source}[${String(e.index)}] = ${String(e.value)}`;
    case "bad_bounds":
      return `log ${e.axis} axis bound invalid: ${e.detail}`;
    case "no_panels":
      return "figure has no panels";
  }
}

function firstNonPositive(cols: readonly { source: string; col: Column }[]): { source: string; index: number; value: number } | null {
  for (const { source, col } of cols) {
    for (let i = 0; i < col.length; i++) {
      const v = col[i] as number;
      if (Number.isFinite(v) && v <= 0) return { source, index: i, value: v };
    }
  }
  return null;
}

function axisCheck(axis: "x" | "y", spec: AxisSpec, cols: { source: string; col: Column }[]): PlotError | null {
  if (spec.scale !== "log") return null;
  for (const [name, b] of [["min", spec.min], ["max", spec.max]] as const) {
    if (b !== undefined && !(b > 0)) return { kind: "bad_bounds", axis, detail: `${name} = ${String(b)} must be > 0` };
  }
  const bad = firstNonPositive(cols);
  return bad === null ? null : { kind: "non_positive", axis, ...bad };
}

/** Reject scenes a log axis cannot draw (non-positive data or bounds); linear scenes always pass. */
export function validateScene(scene: Scene): Result<Scene, PlotError> {
  const xs: { source: string; col: Column }[] = [];
  const ys: { source: string; col: Column }[] = [];
  for (const s of scene.series) { xs.push({ source: `series ${s.id} x`, col: s.x }); ys.push({ source: `series ${s.id} y`, col: s.y }); }
  for (const b of scene.bands ?? []) {
    xs.push({ source: `band ${b.id} x`, col: b.x });
    ys.push({ source: `band ${b.id} lower`, col: b.lower }, { source: `band ${b.id} upper`, col: b.upper });
  }
  for (const f of scene.fits ?? []) { xs.push({ source: `fit ${f.id} x`, col: f.x }); ys.push({ source: `fit ${f.id} y`, col: f.y }); }
  for (const m of scene.markers ?? []) { xs.push({ source: `marker ${m.id} x`, col: [m.x] }); ys.push({ source: `marker ${m.id} y`, col: [m.y] }); }
  for (const l of scene.labels ?? []) { xs.push({ source: `label ${l.id} x`, col: [l.x] }); ys.push({ source: `label ${l.id} y`, col: [l.y] }); }
  for (const sp of scene.spans ?? []) (sp.axis === "x" ? xs : ys).push({ source: `span ${sp.id}`, col: [sp.from, sp.to] });
  const bad = axisCheck("x", scene.xAxis, xs) ?? axisCheck("y", scene.yAxis, ys);
  if (bad !== null) {
    log.warn("scene rejected", { title: scene.title, error: describePlotError(bad) });
    return err(bad);
  }
  return ok(scene);
}

/** One stacked panel: its own y axis and content; the x axis is shared by the figure. */
export interface Panel {
  readonly id: string;
  /** Relative height (default 1). */
  readonly weight?: number;
  readonly yAxis: AxisSpec;
  readonly series: readonly Series[];
  readonly bands?: readonly Band[];
  readonly fits?: readonly FitLine[];
  readonly annotation?: AnnotationBox;
  readonly annotations?: readonly AnnotationBox[];
  readonly markers?: readonly PointMarker[];
  readonly labels?: readonly PointLabel[];
  readonly spans?: readonly Span[];
  readonly legend?: boolean;
}

/** Stacked panels sharing one x range and one plot-area alignment (main plot plus residuals, etc). */
export interface Figure {
  readonly width: number;
  readonly height: number;
  readonly title: string;
  readonly subtitle?: string;
  readonly footer?: string;
  readonly xAxis: AxisSpec;
  readonly panels: readonly Panel[];
  readonly theme: Theme;
}

/** Anything the renderers accept: a single scene or a multi-panel figure. */
export type Drawable = Scene | Figure;

/** True when the drawable is a multi-panel figure. */
export function isFigure(d: Drawable): d is Figure {
  return "panels" in d;
}

function panelXCols(p: Panel): Column[] {
  return [
    ...p.series.map((s) => s.x),
    ...(p.bands ?? []).map((b) => b.x),
    ...(p.fits ?? []).map((f) => f.x),
    (p.markers ?? []).map((m) => m.x),
    (p.labels ?? []).map((l) => l.x),
    ...(p.spans ?? []).filter((s) => s.axis === "x").map((s) => [s.from, s.to]),
  ];
}

/**
 * Split a figure into one Scene per panel: heights follow weights, x bounds are the union over all
 * panels, plot areas are aligned on a common left edge, only the last panel shows x labels, and
 * only the first carries the title. Each scene then flows through the normal layout and draw path.
 */
export function figureScenes(fig: Figure): Scene[] {
  const n = fig.panels.length;
  if (n === 0) return [];
  const xa = resolveAxis(fig.xAxis, fig.panels.flatMap(panelXCols));
  const xAxis: AxisSpec = { ...fig.xAxis, min: xa.lo, max: xa.hi };
  const total = fig.panels.reduce((a, p) => a + (p.weight ?? 1), 0);
  let used = 0;
  const base = fig.panels.map((p, i): Scene => {
    const h = i === n - 1 ? fig.height - used : Math.round((fig.height * (p.weight ?? 1)) / total);
    used += h;
    return {
      width: fig.width, height: h, theme: fig.theme,
      title: i === 0 ? fig.title : "",
      ...(i === 0 && fig.subtitle !== undefined ? { subtitle: fig.subtitle } : {}),
      ...(i === n - 1 && fig.footer !== undefined ? { footer: fig.footer } : {}),
      xAxis, yAxis: p.yAxis, series: p.series,
      ...(p.bands ? { bands: p.bands } : {}), ...(p.fits ? { fits: p.fits } : {}),
      ...(p.annotation ? { annotation: p.annotation } : {}), ...(p.annotations ? { annotations: p.annotations } : {}),
      ...(p.markers ? { markers: p.markers } : {}), ...(p.labels ? { labels: p.labels } : {}), ...(p.spans ? { spans: p.spans } : {}),
      ...(p.legend !== undefined ? { legend: p.legend } : {}),
      xLabels: i === n - 1,
    };
  });
  const plotLeft = Math.max(...base.map((s) => computeLayout(s).plot.x));
  log.debug("figure split", { panels: n, plotLeft });
  return base.map((s) => ({ ...s, plotLeft }));
}

/** Reject a drawable that cannot be rendered (log-axis data errors, empty figures). */
export function validateDrawable(d: Drawable): Result<Drawable, PlotError> {
  if (!isFigure(d)) {
    const r = validateScene(d);
    return r.ok ? ok(d) : r;
  }
  if (d.panels.length === 0) return err({ kind: "no_panels" });
  for (const s of figureScenes(d)) {
    const r = validateScene(s);
    if (!r.ok) return r;
  }
  return ok(d);
}

function shift(op: DrawOp, dy: number): DrawOp {
  switch (op.op) {
    case "rect": case "clipBegin": return { ...op, y: Math.round((op.y + dy) * 100) / 100 };
    case "line": return { ...op, y1: op.y1 + dy, y2: op.y2 + dy };
    case "circle": return { ...op, cy: op.cy + dy };
    case "text": return { ...op, y: Math.round((op.y + dy) * 100) / 100 };
    case "polyline": case "polygon": return { ...op, points: op.points.map((v, i) => (i % 2 === 1 ? v + dy : v)) };
    case "clipEnd": return op;
  }
}

/** Backend-neutral result of building a drawable: the one draw list every backend executes. */
export interface RenderPlan {
  readonly ops: DrawOp[];
  readonly width: number;
  readonly height: number;
  readonly fontFamily: string;
}

/** Build the draw list for a scene or figure (panels are drawn by the same path, then stacked). */
export function renderPlan(d: Drawable): RenderPlan {
  if (!isFigure(d)) {
    return { ops: buildDrawList(d, computeLayout(d)), width: d.width, height: d.height, fontFamily: d.theme.fontFamily };
  }
  const ops: DrawOp[] = [];
  let y = 0;
  for (const s of figureScenes(d)) {
    const panelOps = buildDrawList(s, computeLayout(s));
    ops.push(...(y === 0 ? panelOps : panelOps.map((o) => shift(o, y))));
    y += s.height;
  }
  return { ops, width: d.width, height: d.height, fontFamily: d.theme.fontFamily };
}

/** Same scene with a new x window and/or size; the next draw re-decimates from the full data. */
export function zoomScene(scene: Scene, view: { xMin?: number; xMax?: number; width?: number; height?: number }): Scene {
  return {
    ...scene,
    width: view.width ?? scene.width,
    height: view.height ?? scene.height,
    xAxis: {
      ...scene.xAxis,
      ...(view.xMin !== undefined ? { min: view.xMin } : {}),
      ...(view.xMax !== undefined ? { max: view.xMax } : {}),
    },
  };
}
