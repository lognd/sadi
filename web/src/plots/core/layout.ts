// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
// frob:ticket 01M6W7R3D3KT3NM6JETDDAPA9P
// frob:ticket 01M6WM4ZDY9EHM2BW9312B5SEY
import { getLogger } from "../../api/log";
import { aroundPoint, placeBoxes } from "./place";
import type { PlaceRequest } from "./place";
// frob:ticket 01M6XB9EBAP0ZTTYAMG9NEG3KJ
import { axisTitle, pickColor, seriesCue } from "./scene";
import type { Anchor, AnnotationBox, AxisSpec, Column, MarkerKind, Scene } from "./scene";
import { formatTick, logTicks, niceTicks } from "./ticks";

const log = getLogger("plots.layout");

/** Axis-aligned rectangle in CSS pixels. */
export interface Rect {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
}

/** Affine map from a data domain to a pixel range. */
export interface LinearMap {
  readonly d0: number;
  readonly d1: number;
  readonly r0: number;
  readonly r1: number;
  /** "log" maps through log10 (non-positive values give NaN); omitted means linear. */
  readonly scale?: "log";
}

/** Apply a LinearMap to a data value; NaN for values a log map cannot represent. */
export function mapValue(m: LinearMap, v: number): number {
  if (m.scale === "log") {
    if (!(v > 0)) return NaN;
    const a = Math.log10(m.d0);
    return m.r0 + ((Math.log10(v) - a) / (Math.log10(m.d1) - a)) * (m.r1 - m.r0);
  }
  return m.r0 + ((v - m.d0) / (m.d1 - m.d0)) * (m.r1 - m.r0);
}

/** A labelled tick at a pixel position. */
export interface TickMark {
  readonly value: number;
  readonly px: number;
  readonly label: string;
}

/** One legend row. */
export interface LegendRow {
  readonly kind: "line" | "points" | "band" | "fit";
  readonly label: string;
  readonly color: string;
  /** Series marker glyph (points rows). */
  readonly marker?: MarkerKind;
  /** Dash cue (line rows). */
  readonly dashed?: boolean;
  readonly y: number;
}

/** Legend box and rows, positions in CSS pixels. */
export interface LegendLayout {
  readonly box: Rect;
  readonly rows: readonly LegendRow[];
}

/** Annotation box with one baseline y per line. */
export interface AnnotationLayout {
  readonly box: Rect;
  readonly lines: readonly { readonly text: string; readonly y: number }[];
}

/** A point label after collision-avoided placement; (px, py) is the data point it belongs to. */
export interface LabelLayout {
  readonly text: string;
  readonly box: Rect;
  /** Text baseline y and left x. */
  readonly x: number;
  readonly y: number;
  readonly px: number;
  readonly py: number;
}

/** Every geometric decision for a scene, computed once and shared by canvas, PNG and SVG. */
export interface Layout {
  readonly width: number;
  readonly height: number;
  readonly plot: Rect;
  readonly xMap: LinearMap;
  readonly yMap: LinearMap;
  readonly xTicks: readonly TickMark[];
  readonly yTicks: readonly TickMark[];
  readonly titleY: number;
  readonly subtitleY: number | null;
  readonly xLabelY: number;
  readonly yLabelX: number;
  readonly footerY: number | null;
  readonly legend: LegendLayout | null;
  readonly annotation: AnnotationLayout | null;
  /** Placed extra annotation boxes, in scene order. */
  readonly annotations: readonly AnnotationLayout[];
  readonly labels: readonly LabelLayout[];
}

/** Deterministic text width estimate (no font probing, so every backend agrees). */
export function textWidth(text: string, size: number): number {
  return text.length * size * 0.58;
}

const PAD = 12;
const LEGEND_ROW = 16;
const SWATCH = 24;

function extent(cols: readonly Column[], acc: [number, number], positiveOnly = false): void {
  for (const c of cols) {
    for (let i = 0; i < c.length; i++) {
      const v = c[i] as number;
      if (!Number.isFinite(v) || (positiveOnly && v <= 0)) continue;
      if (v < acc[0]) acc[0] = v;
      if (v > acc[1]) acc[1] = v;
    }
  }
}

/** y + sign * err, element-wise (used to keep error bars inside the autoscaled domain). */
function offsetColumn(y: Column, err: Column, sign: 1 | -1): Column {
  return Array.from({ length: y.length }, (_, i) => (y[i] as number) + sign * (err[i] ?? 0));
}

const AUTO_ORDER: readonly Exclude<Anchor, "auto">[] = ["br", "tr", "bl", "tl"];
const AUTO_SAMPLES = 2000;
/** Label offset rings tried in order: near first, then progressively further from the point. */
const LABEL_GAPS: readonly number[] = [6, 22, 44, 70];

/** Plotted vertices (series, fits, band edges, markers) in pixels, strided so cost is bounded. */
function vertexPixels(scene: Scene, xMap: LinearMap, yMap: LinearMap): { x: number; y: number }[] {
  const cols: [Column, Column][] = [];
  for (const s of scene.series) cols.push([s.x, s.y]);
  for (const f of scene.fits ?? []) cols.push([f.x, f.y]);
  for (const b of scene.bands ?? []) cols.push([b.x, b.lower], [b.x, b.upper]);
  const pts: { x: number; y: number }[] = [];
  for (const [x, y] of cols) {
    const n = Math.min(x.length, y.length);
    const stride = Math.max(1, Math.ceil(n / AUTO_SAMPLES));
    for (let i = 0; i < n; i += stride) {
      const px = mapValue(xMap, x[i] as number);
      const py = mapValue(yMap, y[i] as number);
      if (Number.isFinite(px) && Number.isFinite(py)) pts.push({ x: px, y: py });
    }
  }
  for (const m of scene.markers ?? []) {
    const px = mapValue(xMap, m.x);
    const py = mapValue(yMap, m.y);
    if (Number.isFinite(px) && Number.isFinite(py)) pts.push({ x: px, y: py });
  }
  return pts;
}

/** An axis after domain resolution: final bounds, tick values and a label formatter. */
export interface ResolvedAxis {
  readonly scale: "linear" | "log";
  readonly lo: number;
  readonly hi: number;
  readonly values: readonly number[];
  readonly format: (v: number) => string;
}

/** Resolve an axis spec against the data columns it must cover (linear 1/2/5 or log decade ticks). */
export function resolveAxis(spec: AxisSpec, cols: readonly Column[]): ResolvedAxis {
  const isLog = spec.scale === "log";
  const acc: [number, number] = [Infinity, -Infinity];
  extent(cols, acc, isLog);
  if (!Number.isFinite(acc[0])) {
    acc[0] = isLog ? 1 : 0;
    acc[1] = isLog ? 10 : 1;
  }
  let lo = spec.min;
  let hi = spec.max;
  if (isLog && ((lo !== undefined && !(lo > 0)) || (hi !== undefined && !(hi > 0)))) {
    log.warn("non-positive log bound ignored", { label: spec.label, min: lo, max: hi });
    if (lo !== undefined && !(lo > 0)) lo = undefined;
    if (hi !== undefined && !(hi > 0)) hi = undefined;
  }
  const dmin = lo ?? acc[0];
  const dmax = hi ?? acc[1];
  if (isLog) {
    const t = logTicks(dmin, dmax);
    return { scale: "log", lo: lo ?? t.lo, hi: hi ?? t.hi, values: t.values, format: (v) => formatTick(v, v) };
  }
  const t = niceTicks(dmin, dmax);
  return {
    scale: "linear",
    lo: lo ?? t.values[0] ?? 0,
    hi: hi ?? t.values[t.values.length - 1] ?? 1,
    values: t.values,
    format: (v) => formatTick(v, t.step),
  };
}

function corner(anchor: Exclude<Anchor, "auto">, plot: Rect, w: number, h: number, dy: number): { x: number; y: number } {
  const inset = 8;
  const x = anchor === "tl" || anchor === "bl" ? plot.x + inset : plot.x + plot.w - inset - w;
  const y = anchor === "tl" || anchor === "tr" ? plot.y + inset + dy : plot.y + plot.h - inset - h - dy;
  return { x, y };
}

function boxLayout(box: AnnotationBox, x: number, y: number, w: number, h: number, lh: number): AnnotationLayout {
  return { box: { x, y, w, h }, lines: box.lines.map((text, i) => ({ text, y: y + 4 + (i + 1) * lh - 3 })) };
}

/** Compute the full layout for a scene; pure and deterministic. */
export function computeLayout(scene: Scene): Layout {
  const { theme, width, height } = scene;
  const fs = theme.fontSize;
  const bands = scene.bands ?? [];
  const fits = scene.fits ?? [];
  const spans = scene.spans ?? [];
  const markers = scene.markers ?? [];
  const labels = scene.labels ?? [];

  const xa = resolveAxis(scene.xAxis, [
    ...scene.series.map((s) => s.x),
    ...bands.map((b) => b.x),
    ...fits.map((f) => f.x),
    markers.map((m) => m.x),
    labels.map((l) => l.x),
    ...spans.filter((sp) => sp.axis === "x").map((sp) => [sp.from, sp.to]),
  ]);
  const ya = resolveAxis(scene.yAxis, [
    ...scene.series.map((s) => s.y),
    ...scene.series.flatMap((s) => (s.yErr === undefined ? [] : [offsetColumn(s.y, s.yErr, -1), offsetColumn(s.y, s.yErr, 1)])),
    ...bands.flatMap((b) => [b.lower, b.upper]),
    ...fits.map((f) => f.y),
    markers.map((m) => m.y),
    labels.map((l) => l.y),
    ...spans.filter((sp) => sp.axis === "y").map((sp) => [sp.from, sp.to]),
  ]);
  const showX = scene.xLabels !== false;

  const yLabels = ya.values.map((v) => ya.format(v));
  const maxYTick = Math.max(0, ...yLabels.map((l) => textWidth(l, fs.tick)));
  const left = Math.max(PAD + fs.label + 8 + maxYTick + 8, scene.plotLeft ?? 0);
  const right = PAD + 10;
  const untitled = scene.title === "" && scene.subtitle === undefined;
  let top = untitled ? 8 : PAD + fs.title;
  const titleY = top;
  let subtitleY: number | null = null;
  if (scene.subtitle !== undefined) {
    top += fs.subtitle + 4;
    subtitleY = top;
  }
  if (!untitled) top += 12;
  let bottom = showX ? PAD : 6;
  let footerY: number | null = null;
  if (scene.footer !== undefined) {
    footerY = height - PAD;
    bottom += fs.footer + 6;
  }
  const xLabelY = height - bottom;
  if (showX) bottom += fs.label + 8 + fs.tick + 6;

  const plot: Rect = { x: left, y: top, w: Math.max(1, width - left - right), h: Math.max(1, height - top - bottom) };
  const xMap: LinearMap = { d0: xa.lo, d1: xa.hi, r0: plot.x, r1: plot.x + plot.w, ...(xa.scale === "log" ? { scale: "log" as const } : {}) };
  const yMap: LinearMap = { d0: ya.lo, d1: ya.hi, r0: plot.y + plot.h, r1: plot.y, ...(ya.scale === "log" ? { scale: "log" as const } : {}) };
  const tickMarks = (a: typeof xa, m: LinearMap): TickMark[] =>
    a.values
      .filter((v) => v >= a.lo - Math.abs(a.lo) * 1e-12 - 1e-12 && v <= a.hi + Math.abs(a.hi) * 1e-12 + 1e-12)
      .map((v) => ({ value: v, px: mapValue(m, v), label: a.format(v) }));
  const xTicks = tickMarks(xa, xMap);
  const yTicks = tickMarks(ya, yMap);

  let legend: LegendLayout | null = null;
  if (scene.legend !== false) {
    const entries: { kind: LegendRow["kind"]; label: string; color: string; marker?: MarkerKind; dashed?: boolean }[] = [
      ...scene.series.map((s, i) => ({ kind: s.style, label: s.label, color: pickColor(theme, i, s.color), marker: seriesCue(s, i).marker, dashed: seriesCue(s, i).dashed })),
      ...bands.map((b, i) => ({ kind: "band" as const, label: b.label, color: pickColor(theme, scene.series.length + i, b.color) })),
      ...fits.map((f, i) => ({ kind: "fit" as const, label: f.label, color: pickColor(theme, scene.series.length + bands.length + i, f.color) })),
    ];
    if (entries.length > 0) {
      const w = SWATCH + 6 + Math.max(...entries.map((e) => textWidth(e.label, fs.legend))) + 16;
      const h = entries.length * LEGEND_ROW + 8;
      const pos = corner("tr", plot, w, h, 0);
      legend = {
        box: { x: pos.x, y: pos.y, w, h },
        rows: entries.map((e, i) => ({ ...e, y: pos.y + 4 + i * LEGEND_ROW + LEGEND_ROW / 2 })),
      };
    }
  }

  // Everything below competes for space through one greedy placer: primary annotation, extra
  // annotations, then point labels; each placed box becomes an obstacle for the next.
  const points = vertexPixels(scene, xMap, yMap);
  const obstacles = legend ? [legend.box] : [];
  const lh = fs.annotation + 4;
  const boxRequest = (id: string, a: AnnotationBox, defaultAnchor: Anchor): { req: PlaceRequest; w: number; h: number } => {
    const w = Math.max(...a.lines.map((l) => textWidth(l, fs.annotation))) + 16;
    const h = a.lines.length * lh + 8;
    const requested = a.anchor ?? defaultAnchor;
    // The primary box keeps a fixed anchor exactly; extra boxes fall back to other corners on collision.
    const order = requested === "auto" ? AUTO_ORDER : id === "annotation" ? [requested] : [requested, ...AUTO_ORDER.filter((c) => c !== requested)];
    const candidates = order.map((anc) => {
      const p = corner(anc, plot, w, h, anc === "tr" && legend ? legend.box.h + 8 : 0);
      return { x: p.x, y: p.y };
    });
    return { req: { id, w, h, candidates }, w, h };
  };

  const boxes: { id: string; box: AnnotationBox }[] = [];
  if (scene.annotation !== undefined && scene.annotation.lines.length > 0) boxes.push({ id: "annotation", box: scene.annotation });
  (scene.annotations ?? []).forEach((a, i) => {
    if (a.lines.length > 0) boxes.push({ id: `annotation:${String(i)}`, box: a });
  });
  const reqs = boxes.map((b, i) => boxRequest(b.id, b.box, i === 0 && b.id === "annotation" ? "br" : "auto"));
  const labelReqs: { req: PlaceRequest; text: string; px: number; py: number }[] = [];
  const labelSources = [
    ...labels.map((l) => ({ id: `label:${l.id}`, text: l.text, x: l.x, y: l.y })),
    ...markers.filter((m) => m.label !== undefined && m.label !== "").map((m) => ({ id: `marker:${m.id}`, text: m.label ?? "", x: m.x, y: m.y })),
  ];
  for (const l of labelSources) {
    const px = mapValue(xMap, l.x);
    const py = mapValue(yMap, l.y);
    if (!Number.isFinite(px) || !Number.isFinite(py)) continue;
    const w = textWidth(l.text, fs.annotation) + 8;
    const h = fs.annotation + 4;
    labelReqs.push({ req: { id: l.id, w, h, candidates: LABEL_GAPS.flatMap((g) => aroundPoint(px, py, w, h, g)) }, text: l.text, px, py });
  }
  const placed = placeBoxes([...reqs.map((r) => r.req), ...labelReqs.map((r) => r.req)], { bounds: plot, obstacles, points });
  const boxLayouts: AnnotationLayout[] = [];
  boxes.forEach((b, i) => {
    const pl = placed[i];
    const rq = reqs[i];
    if (pl === undefined || rq === undefined) return;
    boxLayouts.push(boxLayout(b.box, pl.box.x, pl.box.y, rq.w, rq.h, lh));
    log.debug("annotation placed", { id: b.id, x: pl.box.x, y: pl.box.y, penalty: pl.score });
  });
  const hasPrimary = boxes[0]?.id === "annotation";
  const annotation = hasPrimary ? (boxLayouts[0] ?? null) : null;
  const extra = hasPrimary ? boxLayouts.slice(1) : boxLayouts;
  const labelLayouts: LabelLayout[] = labelReqs.map((r, k) => {
    const pl = placed[boxes.length + k];
    const box = pl?.box ?? { x: r.px, y: r.py, w: r.req.w, h: r.req.h };
    return { text: r.text, box, x: box.x + 4, y: box.y + box.h - 5, px: r.px, py: r.py };
  });

  log.debug("layout computed", {
    width, height, xTicks: xTicks.length, yTicks: yTicks.length, title: scene.title,
    xTitle: axisTitle(scene.xAxis), xScale: xa.scale, yScale: ya.scale, labels: labelLayouts.length, annotations: boxes.length,
  });
  return {
    width, height, plot, xMap, yMap, xTicks, yTicks, titleY, subtitleY, xLabelY,
    yLabelX: PAD + fs.label - 3, footerY, legend, annotation, annotations: extra, labels: labelLayouts,
  };
}
