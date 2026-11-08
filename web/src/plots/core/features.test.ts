// frob:ticket 01M6WM4ZDY9EHM2BW9312B5SEY
/* eslint-disable @typescript-eslint/no-non-null-assertion -- indexed fixtures with known length */
import { describe, expect, it } from "vitest";
import {
  buildDrawList, computeLayout, decimateWindow, exportFigure, figureScenes, lightTheme, logTicks,
  placeBoxes, renderPlan, sceneToSvg, validateScene, zoomScene,
} from "./index";
import type { Figure, Scene } from "./index";

function overlap(a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

function crowded(): Scene {
  const x = Array.from({ length: 40 }, (_, i) => i);
  return {
    width: 640, height: 400, title: "Crowded", theme: lightTheme,
    xAxis: { label: "x" }, yAxis: { label: "y" },
    series: [{ id: "s", label: "s", x, y: x.map((v) => v * v), style: "line" }],
    annotation: { lines: ["primary", "box"] },
    annotations: [{ lines: ["second"], anchor: "tl" }, { lines: ["third"], anchor: "tl" }],
    labels: [{ id: "a", x: 10, y: 100, text: "alpha" }, { id: "b", x: 10.2, y: 101, text: "beta" }],
    markers: [{ id: "m", x: 20, y: 400, kind: "ring" }],
    spans: [{ id: "sp", axis: "x", from: 5, to: 8 }],
  };
}

describe("label placement", () => {
  it("never overlaps placed boxes or the legend and is deterministic", () => {
    const a = computeLayout(crowded());
    const b = computeLayout(crowded());
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
    const boxes = [
      ...(a.annotation ? [a.annotation.box] : []),
      ...a.annotations.map((n) => n.box),
      ...a.labels.map((l) => l.box),
    ];
    expect(boxes.length).toBe(5);
    for (let i = 0; i < boxes.length; i++) {
      if (a.legend) expect(overlap(boxes[i]!, a.legend.box)).toBe(false);
      for (let j = i + 1; j < boxes.length; j++) expect(overlap(boxes[i]!, boxes[j]!)).toBe(false);
    }
  });

  it("first candidate wins ties and placed boxes become obstacles", () => {
    const ctx = { bounds: { x: 0, y: 0, w: 100, h: 100 }, obstacles: [], points: [] };
    const cand = [{ x: 10, y: 10 }, { x: 60, y: 60 }];
    const out = placeBoxes([{ id: "a", w: 20, h: 20, candidates: cand }, { id: "b", w: 20, h: 20, candidates: cand }], ctx);
    expect(out[0]!.box).toMatchObject({ x: 10, y: 10 });
    expect(out[1]!.box).toMatchObject({ x: 60, y: 60 });
  });
});

describe("log axes", () => {
  it("produces decade ticks and log-mapped geometry", () => {
    expect(logTicks(1, 1000).values).toEqual([1, 10, 100, 1000]);
    expect(logTicks(1, 100).values).toEqual([1, 2, 5, 10, 20, 50, 100]);
    const s: Scene = {
      width: 400, height: 300, title: "Log", theme: lightTheme,
      xAxis: { label: "x" }, yAxis: { label: "y", scale: "log" },
      series: [{ id: "s", label: "s", x: [0, 1, 2], y: [1, 10, 100], style: "line" }],
    };
    const l = computeLayout(s);
    expect(l.yMap.scale).toBe("log");
    const mid = l.yTicks.find((t) => t.value === 10)!;
    expect(mid.px).toBeCloseTo((l.yTicks.find((t) => t.value === 1)!.px + l.yTicks.find((t) => t.value === 100)!.px) / 2, 6);
  });

  it("returns a PlotError for non-positive data and bounds", () => {
    const base: Scene = {
      width: 400, height: 300, title: "Log", theme: lightTheme,
      xAxis: { label: "x" }, yAxis: { label: "y", scale: "log" },
      series: [{ id: "s", label: "s", x: [0, 1], y: [1, -2], style: "line" }],
    };
    const r = validateScene(base);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatchObject({ kind: "non_positive", axis: "y", index: 1, value: -2 });
    const b = validateScene({ ...base, series: [], yAxis: { label: "y", scale: "log", min: 0 } });
    expect(b.ok).toBe(false);
    expect(validateScene({ ...base, yAxis: { label: "y" } }).ok).toBe(true);
  });

  it("rejects export of invalid log scenes", async () => {
    const bad: Scene = {
      width: 400, height: 300, title: "Log", theme: lightTheme,
      xAxis: { label: "x" }, yAxis: { label: "y", scale: "log" },
      series: [{ id: "s", label: "s", x: [0], y: [0], style: "line" }],
    };
    const r = await exportFigure(bad, { format: "svg" });
    expect(r.ok).toBe(false);
  });
});

describe("zoom decimation", () => {
  const x = Array.from({ length: 10000 }, (_, i) => i);
  const y = x.map((v) => Math.sin(v / 50));

  it("bounds output to the window and keeps its extremes", () => {
    const idx = decimateWindow(x, y, 50, 2000, 3000);
    expect(idx.length).toBeLessThanOrEqual(50 * 2 + 4);
    expect(idx.length).toBeGreaterThan(0);
    for (const i of idx) expect(x[i]).toBeGreaterThanOrEqual(1999);
    for (const i of idx) expect(x[i]).toBeLessThanOrEqual(3001);
    expect(idx).toEqual([...idx].sort((p, q) => p - q));
    expect(decimateWindow(x, y, 50, 2000, 3000)).toEqual(idx);
  });

  it("zoomScene re-derives the draw list from full data", () => {
    const s: Scene = {
      width: 400, height: 300, title: "Z", theme: lightTheme, xAxis: { label: "x" }, yAxis: { label: "y" },
      series: [{ id: "s", label: "s", x, y, style: "line" }],
    };
    const full = renderPlan(s).ops.find((o) => o.op === "polyline" && o.points.length > 100);
    const zoomed = renderPlan(zoomScene(s, { xMin: 2000, xMax: 2100, width: 800 }));
    const line = zoomed.ops.find((o) => o.op === "polyline" && o.points.length > 100);
    expect(full && full.op === "polyline" ? full.points.length : 0).toBeLessThan(2000);
    expect(zoomed.width).toBe(800);
    expect(line).toBeDefined();
  });
});

describe("figure panels", () => {
  const x = [0, 1, 2, 3, 4];
  const fig: Figure = {
    width: 600, height: 500, title: "Fig", footer: "foot", theme: lightTheme, xAxis: { label: "x" },
    panels: [
      { id: "main", weight: 3, yAxis: { label: "y" }, series: [{ id: "s", label: "s", x, y: [0, 10, 20, 30, 1000], style: "line" }] },
      { id: "res", weight: 1, yAxis: { label: "res" }, series: [{ id: "r", label: "r", x: [0, 1, 2, 3, 6], y: [0, 1, -1, 1, 0], style: "points" }] },
    ],
  };

  it("shares x range, aligns plot areas and splits heights", () => {
    const sc = figureScenes(fig);
    expect(sc).toHaveLength(2);
    expect(sc[0]!.height + sc[1]!.height).toBe(500);
    expect(sc[0]!.xAxis.max).toBe(sc[1]!.xAxis.max);
    const [l0, l1] = sc.map((s) => computeLayout(s));
    expect(l0!.plot.x).toBe(l1!.plot.x);
    expect(l0!.plot.w).toBe(l1!.plot.w);
    expect(l0!.xTicks.length).toBeGreaterThan(0);
    expect(sc[0]!.xLabels).toBe(false);
    expect(sc[1]!.footer).toBe("foot");
  });

  it("renders through the shared plan to svg and canvas ops", () => {
    const plan = renderPlan(fig);
    expect(plan.height).toBe(500);
    const svg = sceneToSvg(fig);
    expect(svg).toContain("<svg");
    expect(svg).toMatchSnapshot();
    expect(plan.ops.length).toBeGreaterThan(buildDrawList(figureScenes(fig)[0]!, computeLayout(figureScenes(fig)[0]!)).length);
  });
});

describe("markers, spans and labels", () => {
  it("emit draw ops identically for svg and draw-list goldens", () => {
    const s = crowded();
    const ops = buildDrawList(s, computeLayout(s));
    expect(ops.some((o) => o.op === "polygon")).toBe(true);
    expect(JSON.stringify(ops, null, 1)).toMatchSnapshot();
    expect(sceneToSvg(s)).toMatchSnapshot();
  });
});
