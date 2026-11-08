// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
// frob:ticket 01M6W7R3D3KT3NM6JETDDAPA9P
import { getLogger } from "../../api/log";
import { decimateIndices } from "./decimate";
import { mapValue } from "./layout";
import type { Layout } from "./layout";
import { axisTitle, pickColor } from "./scene";
import type { Column, Scene } from "./scene";

const log = getLogger("plots.drawlist");

/** Backend-neutral drawing primitive; canvas and SVG both execute exactly this list. */
export type DrawOp =
  | { readonly op: "rect"; readonly x: number; readonly y: number; readonly w: number; readonly h: number; readonly fill?: string; readonly stroke?: string; readonly strokeWidth?: number }
  | { readonly op: "line"; readonly x1: number; readonly y1: number; readonly x2: number; readonly y2: number; readonly stroke: string; readonly strokeWidth: number }
  | { readonly op: "polyline"; readonly points: readonly number[]; readonly stroke: string; readonly strokeWidth: number; readonly dashed: boolean }
  | { readonly op: "polygon"; readonly points: readonly number[]; readonly fill: string; readonly opacity: number }
  | { readonly op: "circle"; readonly cx: number; readonly cy: number; readonly r: number; readonly fill?: string; readonly stroke?: string; readonly strokeWidth?: number }
  | { readonly op: "text"; readonly x: number; readonly y: number; readonly text: string; readonly size: number; readonly color: string; readonly anchor: "start" | "middle" | "end"; readonly bold?: boolean; readonly rotate?: number }
  | { readonly op: "clipBegin"; readonly x: number; readonly y: number; readonly w: number; readonly h: number }
  | { readonly op: "clipEnd" };

const r2 = (v: number): number => Math.round(v * 100) / 100;

function project(layout: Layout, x: Column, y: Column, idx: readonly number[]): number[] {
  const out: number[] = [];
  for (const i of idx) {
    out.push(r2(mapValue(layout.xMap, x[i] as number)), r2(mapValue(layout.yMap, y[i] as number)));
  }
  return out;
}

/** Vertices for a curve after decimation to the plot width. */
function curve(layout: Layout, x: Column, y: Column): number[] {
  return project(layout, x, y, decimateIndices(x, y, Math.ceil(layout.plot.w)));
}

/** Build the ordered draw list for a scene and its layout (no I/O, no canvas). */
export function buildDrawList(scene: Scene, layout: Layout): DrawOp[] {
  const { theme } = scene;
  const fs = theme.fontSize;
  const { plot } = layout;
  const ops: DrawOp[] = [];
  ops.push({ op: "rect", x: 0, y: 0, w: layout.width, h: layout.height, fill: theme.background });
  ops.push({ op: "rect", x: r2(plot.x), y: r2(plot.y), w: r2(plot.w), h: r2(plot.h), fill: theme.plotBackground });
  for (const t of layout.xTicks) {
    ops.push({ op: "line", x1: r2(t.px), y1: r2(plot.y), x2: r2(t.px), y2: r2(plot.y + plot.h), stroke: theme.grid, strokeWidth: 1 });
  }
  for (const t of layout.yTicks) {
    ops.push({ op: "line", x1: r2(plot.x), y1: r2(t.px), x2: r2(plot.x + plot.w), y2: r2(t.px), stroke: theme.grid, strokeWidth: 1 });
  }

  ops.push({ op: "clipBegin", x: r2(plot.x), y: r2(plot.y), w: r2(plot.w), h: r2(plot.h) });
  const bands = scene.bands ?? [];
  const fits = scene.fits ?? [];
  bands.forEach((b, i) => {
    const color = pickColor(theme, scene.series.length + i, b.color);
    const idx = decimateIndices(b.x, b.upper, Math.ceil(plot.w));
    const up = project(layout, b.x, b.upper, idx);
    const lo = project(layout, b.x, b.lower, idx);
    const back: number[] = [];
    for (let k = lo.length - 2; k >= 0; k -= 2) back.push(lo[k] as number, lo[k + 1] as number);
    ops.push({ op: "polygon", points: [...up, ...back], fill: color, opacity: theme.bandOpacity });
  });
  fits.forEach((f, i) => {
    const color = pickColor(theme, scene.series.length + bands.length + i, f.color);
    ops.push({ op: "polyline", points: curve(layout, f.x, f.y), stroke: color, strokeWidth: theme.fitWidth, dashed: true });
  });
  scene.series.forEach((s, i) => {
    const color = pickColor(theme, i, s.color);
    if (s.style === "line") {
      ops.push({ op: "polyline", points: curve(layout, s.x, s.y), stroke: color, strokeWidth: theme.lineWidth, dashed: s.dashed === true });
      return;
    }
    const idx = decimateIndices(s.x, s.y, Math.ceil(plot.w));
    const pts = project(layout, s.x, s.y, idx);
    if (s.yErr !== undefined) {
      for (const i of idx) {
        const yv = s.y[i] as number;
        const e = s.yErr[i] as number;
        const px = r2(mapValue(layout.xMap, s.x[i] as number));
        const top = r2(mapValue(layout.yMap, yv + e));
        const bot = r2(mapValue(layout.yMap, yv - e));
        ops.push({ op: "line", x1: px, y1: top, x2: px, y2: bot, stroke: color, strokeWidth: theme.lineWidth });
        ops.push({ op: "line", x1: r2(px - 3), y1: top, x2: r2(px + 3), y2: top, stroke: color, strokeWidth: theme.lineWidth });
        ops.push({ op: "line", x1: r2(px - 3), y1: bot, x2: r2(px + 3), y2: bot, stroke: color, strokeWidth: theme.lineWidth });
      }
    }
    for (let k = 0; k < pts.length; k += 2) {
      ops.push(...marker(s.marker ?? "filled", pts[k] as number, pts[k + 1] as number, theme.markerRadius, color));
    }
  });
  ops.push({ op: "clipEnd" });

  ops.push({ op: "rect", x: r2(plot.x), y: r2(plot.y), w: r2(plot.w), h: r2(plot.h), stroke: theme.axis, strokeWidth: 1 });
  for (const t of layout.xTicks) {
    ops.push({ op: "line", x1: r2(t.px), y1: r2(plot.y + plot.h), x2: r2(t.px), y2: r2(plot.y + plot.h + 4), stroke: theme.axis, strokeWidth: 1 });
    ops.push({ op: "text", x: r2(t.px), y: r2(plot.y + plot.h + 6 + fs.tick), text: t.label, size: fs.tick, color: theme.text, anchor: "middle" });
  }
  for (const t of layout.yTicks) {
    ops.push({ op: "line", x1: r2(plot.x - 4), y1: r2(t.px), x2: r2(plot.x), y2: r2(t.px), stroke: theme.axis, strokeWidth: 1 });
    ops.push({ op: "text", x: r2(plot.x - 7), y: r2(t.px + fs.tick * 0.35), text: t.label, size: fs.tick, color: theme.text, anchor: "end" });
  }
  ops.push({ op: "text", x: r2(plot.x + plot.w / 2), y: r2(layout.xLabelY), text: axisTitle(scene.xAxis), size: fs.label, color: theme.text, anchor: "middle" });
  ops.push({ op: "text", x: r2(layout.yLabelX), y: r2(plot.y + plot.h / 2), text: axisTitle(scene.yAxis), size: fs.label, color: theme.text, anchor: "middle", rotate: -90 });
  ops.push({ op: "text", x: r2(plot.x), y: r2(layout.titleY), text: scene.title, size: fs.title, color: theme.text, anchor: "start", bold: true });
  if (scene.subtitle !== undefined && layout.subtitleY !== null) {
    ops.push({ op: "text", x: r2(plot.x), y: r2(layout.subtitleY), text: scene.subtitle, size: fs.subtitle, color: theme.mutedText, anchor: "start" });
  }
  if (scene.footer !== undefined && layout.footerY !== null) {
    ops.push({ op: "text", x: r2(plot.x), y: r2(layout.footerY), text: scene.footer, size: fs.footer, color: theme.mutedText, anchor: "start" });
  }

  if (layout.legend) {
    const b = layout.legend.box;
    ops.push({ op: "rect", x: r2(b.x), y: r2(b.y), w: r2(b.w), h: r2(b.h), fill: theme.annotationFill, stroke: theme.annotationStroke, strokeWidth: 1 });
    for (const row of layout.legend.rows) {
      const sx = b.x + 6;
      if (row.kind === "band") {
        ops.push({ op: "rect", x: r2(sx), y: r2(row.y - 4), w: 18, h: 8, fill: row.color });
      } else if (row.kind === "points") {
        ops.push(...marker("filled", r2(sx + 9), r2(row.y), theme.markerRadius, row.color));
      } else {
        ops.push({ op: "polyline", points: [r2(sx), r2(row.y), r2(sx + 18), r2(row.y)], stroke: row.color, strokeWidth: row.kind === "fit" ? theme.fitWidth : theme.lineWidth, dashed: row.kind === "fit" });
      }
      ops.push({ op: "text", x: r2(sx + 24), y: r2(row.y + fs.legend * 0.35), text: row.label, size: fs.legend, color: theme.text, anchor: "start" });
    }
  }
  if (layout.annotation) {
    const b = layout.annotation.box;
    ops.push({ op: "rect", x: r2(b.x), y: r2(b.y), w: r2(b.w), h: r2(b.h), fill: theme.annotationFill, stroke: theme.annotationStroke, strokeWidth: 1 });
    for (const l of layout.annotation.lines) {
      ops.push({ op: "text", x: r2(b.x + 8), y: r2(l.y), text: l.text, size: fs.annotation, color: theme.text, anchor: "start" });
    }
  }
  log.debug("draw list built", { ops: ops.length, series: scene.series.length });
  return ops;
}

function marker(kind: "filled" | "ring" | "cross", cx: number, cy: number, r: number, color: string): DrawOp[] {
  if (kind === "filled") return [{ op: "circle", cx, cy, r, fill: color }];
  if (kind === "ring") return [{ op: "circle", cx, cy, r, stroke: color, strokeWidth: 1.25 }];
  return [
    { op: "line", x1: r2(cx - r), y1: r2(cy - r), x2: r2(cx + r), y2: r2(cy + r), stroke: color, strokeWidth: 1.25 },
    { op: "line", x1: r2(cx - r), y1: r2(cy + r), x2: r2(cx + r), y2: r2(cy - r), stroke: color, strokeWidth: 1.25 },
  ];
}
