// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
// frob:ticket 01M6W7R3D3KT3NM6JETDDAPA9P
import { getLogger } from "../../api/log";
import { axisTitle, pickColor } from "./scene";
import type { Anchor, Column, Scene } from "./scene";
import { formatTick, niceTicks } from "./ticks";

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
}

/** Apply a LinearMap to a data value. */
export function mapValue(m: LinearMap, v: number): number {
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
}

/** Deterministic text width estimate (no font probing, so every backend agrees). */
export function textWidth(text: string, size: number): number {
  return text.length * size * 0.58;
}

const PAD = 12;
const LEGEND_ROW = 16;
const SWATCH = 24;

function extent(cols: readonly Column[], acc: [number, number]): void {
  for (const c of cols) {
    for (let i = 0; i < c.length; i++) {
      const v = c[i] as number;
      if (!Number.isFinite(v)) continue;
      if (v < acc[0]) acc[0] = v;
      if (v > acc[1]) acc[1] = v;
    }
  }
}

/** y + sign * err, element-wise (used to keep error bars inside the autoscaled domain). */
function offsetColumn(y: Column, err: Column, sign: 1 | -1): Column {
  return Array.from({ length: y.length }, (_, i) => (y[i] as number) + sign * (err[i] ?? 0));
}

function overlaps(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

const AUTO_ORDER: readonly Exclude<Anchor, "auto">[] = ["br", "tr", "bl", "tl"];
const AUTO_SAMPLES = 2000;

/** Count plotted vertices (series, fits, band edges) that fall inside `box`; strided so cost is bounded. */
function hitsInBox(scene: Scene, xMap: LinearMap, yMap: LinearMap, box: Rect): number {
  const cols: [Column, Column][] = [];
  for (const s of scene.series) cols.push([s.x, s.y]);
  for (const f of scene.fits ?? []) cols.push([f.x, f.y]);
  for (const b of scene.bands ?? []) cols.push([b.x, b.lower], [b.x, b.upper]);
  let hits = 0;
  for (const [x, y] of cols) {
    const n = Math.min(x.length, y.length);
    const stride = Math.max(1, Math.ceil(n / AUTO_SAMPLES));
    for (let i = 0; i < n; i += stride) {
      const px = mapValue(xMap, x[i] as number);
      const py = mapValue(yMap, y[i] as number);
      if (px >= box.x && px <= box.x + box.w && py >= box.y && py <= box.y + box.h) hits++;
    }
  }
  return hits;
}

function domain(
  lo: number | undefined,
  hi: number | undefined,
  cols: readonly Column[],
): { min: number; max: number; fixed: boolean } {
  const acc: [number, number] = [Infinity, -Infinity];
  extent(cols, acc);
  if (!Number.isFinite(acc[0])) {
    acc[0] = 0;
    acc[1] = 1;
  }
  const fixed = lo !== undefined && hi !== undefined;
  return { min: lo ?? acc[0], max: hi ?? acc[1], fixed };
}

function corner(anchor: Exclude<Anchor, "auto">, plot: Rect, w: number, h: number, dy: number): { x: number; y: number } {
  const inset = 8;
  const x = anchor === "tl" || anchor === "bl" ? plot.x + inset : plot.x + plot.w - inset - w;
  const y = anchor === "tl" || anchor === "tr" ? plot.y + inset + dy : plot.y + plot.h - inset - h - dy;
  return { x, y };
}

/** Compute the full layout for a scene; pure and deterministic. */
export function computeLayout(scene: Scene): Layout {
  const { theme, width, height } = scene;
  const fs = theme.fontSize;
  const bands = scene.bands ?? [];
  const fits = scene.fits ?? [];

  const xd = domain(scene.xAxis.min, scene.xAxis.max, [
    ...scene.series.map((s) => s.x),
    ...bands.map((b) => b.x),
    ...fits.map((f) => f.x),
  ]);
  const yd = domain(scene.yAxis.min, scene.yAxis.max, [
    ...scene.series.map((s) => s.y),
    ...scene.series.flatMap((s) => (s.yErr === undefined ? [] : [offsetColumn(s.y, s.yErr, -1), offsetColumn(s.y, s.yErr, 1)])),
    ...bands.flatMap((b) => [b.lower, b.upper]),
    ...fits.map((f) => f.y),
  ]);
  const xt = niceTicks(xd.min, xd.max);
  const yt = niceTicks(yd.min, yd.max);
  const xLo = scene.xAxis.min ?? xt.values[0] ?? 0;
  const xHi = scene.xAxis.max ?? xt.values[xt.values.length - 1] ?? 1;
  const yLo = scene.yAxis.min ?? yt.values[0] ?? 0;
  const yHi = scene.yAxis.max ?? yt.values[yt.values.length - 1] ?? 1;

  const yLabels = yt.values.map((v) => formatTick(v, yt.step));
  const maxYTick = Math.max(...yLabels.map((l) => textWidth(l, fs.tick)));
  const left = PAD + fs.label + 8 + maxYTick + 8;
  const right = PAD + 10;
  let top = PAD + fs.title;
  const titleY = top;
  let subtitleY: number | null = null;
  if (scene.subtitle !== undefined) {
    top += fs.subtitle + 4;
    subtitleY = top;
  }
  top += 12;
  let bottom = PAD;
  let footerY: number | null = null;
  if (scene.footer !== undefined) {
    footerY = height - PAD;
    bottom += fs.footer + 6;
  }
  const xLabelY = height - bottom;
  bottom += fs.label + 8 + fs.tick + 6;

  const plot: Rect = { x: left, y: top, w: Math.max(1, width - left - right), h: Math.max(1, height - top - bottom) };
  const xMap: LinearMap = { d0: xLo, d1: xHi, r0: plot.x, r1: plot.x + plot.w };
  const yMap: LinearMap = { d0: yLo, d1: yHi, r0: plot.y + plot.h, r1: plot.y };
  const xTicks = xt.values
    .filter((v) => v >= xLo - 1e-12 && v <= xHi + 1e-12)
    .map((v) => ({ value: v, px: mapValue(xMap, v), label: formatTick(v, xt.step) }));
  const yTicks = yt.values
    .filter((v) => v >= yLo - 1e-12 && v <= yHi + 1e-12)
    .map((v) => ({ value: v, px: mapValue(yMap, v), label: formatTick(v, yt.step) }));

  let legend: LegendLayout | null = null;
  if (scene.legend !== false) {
    const entries: { kind: LegendRow["kind"]; label: string; color: string }[] = [
      ...scene.series.map((s, i) => ({ kind: s.style, label: s.label, color: pickColor(theme, i, s.color) })),
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

  let annotation: AnnotationLayout | null = null;
  if (scene.annotation !== undefined && scene.annotation.lines.length > 0) {
    const requested = scene.annotation.anchor ?? "br";
    const lh = fs.annotation + 4;
    const w = Math.max(...scene.annotation.lines.map((l) => textWidth(l, fs.annotation))) + 16;
    const h = scene.annotation.lines.length * lh + 8;
    const place = (a: Exclude<Anchor, "auto">): { x: number; y: number } =>
      corner(a, plot, w, h, a === "tr" && legend ? legend.box.h + 8 : 0);
    let anchor: Exclude<Anchor, "auto"> = "br";
    if (requested === "auto") {
      let best = Infinity;
      for (const a of AUTO_ORDER) {
        const p = place(a);
        const box = { x: p.x, y: p.y, w, h };
        const score = hitsInBox(scene, xMap, yMap, box) + (legend && overlaps(box, legend.box) ? 1e6 : 0);
        if (score < best) {
          best = score;
          anchor = a;
        }
      }
      log.debug("annotation auto-placed", { anchor, hits: best });
    } else {
      anchor = requested;
    }
    const pos = place(anchor);
    annotation = {
      box: { x: pos.x, y: pos.y, w, h },
      lines: scene.annotation.lines.map((text, i) => ({ text, y: pos.y + 4 + (i + 1) * lh - 3 })),
    };
  }

  log.debug("layout computed", { width, height, xTicks: xTicks.length, yTicks: yTicks.length, title: scene.title, xTitle: axisTitle(scene.xAxis) });
  return {
    width, height, plot, xMap, yMap, xTicks, yTicks, titleY, subtitleY, xLabelY,
    yLabelX: PAD + fs.label - 3, footerY, legend, annotation,
  };
}
