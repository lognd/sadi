// frob:ticket 01M72PGN6FQEXXCFGXA3EMAPTS
// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
// frob:ticket 01M6W7R3D3KT3NM6JETDDAPA9P
import { describe, expect, it } from "vitest";
import {
  buildDrawList, computeLayout, decimateIndices, exportFigure, withExportTheme, formatTick, lightTheme, niceTicks,
  paintScene, renderToCanvas, sceneToSvg,
} from "./index";
import type { Ctx2D, ExportCanvas, Scene } from "./index";

function scene(n = 6): Scene {
  const x = Array.from({ length: n }, (_, i) => i * 2);
  const y = x.map((v) => 10 * v + 3);
  return {
    width: 640, height: 400, title: "Calibration", subtitle: "run 1", footer: "Bands are 95 % intervals",
    xAxis: { label: "Displacement", unit: "mm" }, yAxis: { label: "Force", unit: "N" },
    series: [{ id: "d", label: "captured", x, y, style: "points" }],
    bands: [{ id: "b", label: "95 % band", x, lower: y.map((v) => v - 5), upper: y.map((v) => v + 5) }],
    fits: [{ id: "f", label: "fit", x, y }],
    annotation: { lines: ["F = 10.0 x + 3.0", "r^2 = 0.9994"] },
    theme: lightTheme,
  };
}

/** Recording context: logs every call and property set as a string. */
function recorder(): { ctx: Ctx2D; log: string[] } {
  const log: string[] = [];
  const target: Record<string, unknown> = {};
  const ctx = new Proxy(target, {
    get(t, k: string) {
      if (k in t) return t[k];
      return (...a: unknown[]) => { log.push(`${k}(${a.map(String).join(",")})`); };
    },
    set(t, k: string, v) { t[k] = v; log.push(`${k}=${String(v)}`); return true; },
  }) as unknown as Ctx2D;
  return { ctx, log };
}

describe("ticks", () => {
  it("chooses 1/2/5 steps and formats with matching decimals", () => {
    const t = niceTicks(0, 10);
    expect(t.values).toEqual([0, 2, 4, 6, 8, 10]);
    expect(niceTicks(0, 0.5).values.map((v) => formatTick(v, niceTicks(0, 0.5).step))).toEqual(["0", "0.1", "0.2", "0.3", "0.4", "0.5"]);
    expect(formatTick(2500000, 500000)).toBe("2.5e6");
    expect(formatTick(0.00002, 0.00001)).toBe("2e-5");
    expect(niceTicks(3, 3).values.length).toBeGreaterThan(1);
  });
});

describe("layout", () => {
  it("is deterministic and keeps the plot inside the canvas", () => {
    const a = computeLayout(scene());
    const b = computeLayout(scene());
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
    expect(a.plot.x + a.plot.w).toBeLessThanOrEqual(640);
    expect(a.plot.y + a.plot.h).toBeLessThanOrEqual(400);
    expect(a.legend).not.toBeNull();
    expect(a.annotation).not.toBeNull();
  });
});

describe("decimation", () => {
  it("bounds 100k points and keeps extremes", () => {
    const n = 100_000;
    const x = new Float64Array(n);
    const y = new Float64Array(n);
    for (let i = 0; i < n; i++) { x[i] = i; y[i] = Math.sin(i / 300) + (i === 54321 ? 5 : 0); }
    const idx = decimateIndices(x, y, 800);
    expect(idx.length).toBeLessThanOrEqual(2 * 800 + 2);
    expect(idx).toContain(54321);
    expect(idx[0]).toBe(0);
    expect(idx[idx.length - 1]).toBe(n - 1);
    const s: Scene = { ...scene(), series: [{ id: "t", label: "t", x, y, style: "line" }], bands: [], fits: [] };
    const ops = buildDrawList(s, computeLayout(s));
    const line = ops.find((o) => o.op === "polyline");
    expect(line?.op === "polyline" ? line.points.length / 2 : Infinity).toBeLessThanOrEqual(2 * 600 + 2);
  });
});

describe("svg", () => {
  it("matches the snapshot", () => {
    expect(sceneToSvg(scene())).toMatchSnapshot();
  });
  it("escapes text", () => {
    const s = { ...scene(), title: "a<b & c" };
    expect(sceneToSvg(s)).toContain("a&lt;b &amp; c");
  });
});

describe("canvas draw calls", () => {
  it("records a stable golden call sequence", () => {
    const { ctx, log } = recorder();
    paintScene(ctx, scene(), 2);
    expect(log.slice(0, 3)).toEqual(["save()", "scale(2,2)", "fillStyle=#f8f6ee"]);
    expect(log.join("\n")).toMatchSnapshot();
  });
});

describe("exportFigure", () => {
  function factory(rec: { log: string[]; size: number[] }): (w: number, h: number) => ExportCanvas {
    return (w, h) => {
      const r = recorder();
      rec.log = r.log;
      rec.size = [w, h];
      return { width: w, height: h, getContext: () => r.ctx, toBlob: (cb) => { cb(new Blob(["png"], { type: "image/png" })); } };
    };
  }
  it("png at 300 dpi uses identical layout, scaled", async () => {
    const lo = { log: [] as string[], size: [0, 0] };
    const hi = { log: [] as string[], size: [0, 0] };
    const a = await exportFigure(scene(), { format: "png", dpi: 96 }, { createCanvas: factory(lo) });
    const b = await exportFigure(scene(), { format: "png", dpi: 300 }, { createCanvas: factory(hi) });
    expect(a.ok && b.ok).toBe(true);
    expect(hi.size).toEqual([2000, 1250]);
    expect(lo.size).toEqual([640, 400]);
    const strip = (l: string[]): string[] => l.filter((c) => !c.startsWith("scale("));
    expect(strip(hi.log)).toEqual(strip(lo.log));
    expect(hi.log[1]).toBe("scale(3.125,3.125)");
  });
  it("svg export uses white background and sans fonts", async () => {
    const r = await exportFigure(scene(), { format: "svg" });
    expect(r.ok && r.value.text).toContain("Helvetica");
    expect(r.ok && r.value.text).toContain("#ffffff");
    expect(r.ok && r.value.text).not.toContain("#f8f6ee");
  });

  it("svg returns text and blob; bad dpi is an error", async () => {
    const r = await exportFigure(scene(), { format: "svg" });
    expect(r.ok && r.value.text).toBe(sceneToSvg(withExportTheme(scene())));
    const bad = await exportFigure(scene(), { format: "png", dpi: -1 }, { createCanvas: factory({ log: [], size: [] }) });
    expect(bad.ok).toBe(false);
  });
});

describe("renderToCanvas", () => {
  it("sizes the backing store by the device pixel ratio", () => {
    const r = recorder();
    const canvas = { width: 0, height: 0, style: { width: "", height: "" }, getContext: () => r.ctx };
    renderToCanvas(canvas as unknown as HTMLCanvasElement, scene(), { dpr: 2 });
    expect([canvas.width, canvas.height]).toEqual([1280, 800]);
    expect(canvas.style.width).toBe("640px");
    expect(r.log[1]).toBe("scale(2,2)");
  });
});

describe("error bars and auto annotation placement", () => {
  it("draws capped error bars and widens the autoscaled domain", () => {
    const s: Scene = {
      ...scene(3),
      series: [{ id: "d", label: "d", x: [0, 1], y: [5, 6], style: "points", yErr: [1, 1] }],
      bands: [], fits: [], annotation: undefined,
    };
    const ops = buildDrawList(s, computeLayout(s));
    const bars = ops.filter((o) => o.op === "line" && o.strokeWidth === s.theme.lineWidth);
    expect(bars.length).toBeGreaterThanOrEqual(6);
    expect(computeLayout(s).yTicks[0]?.value).toBeLessThanOrEqual(4);
  });

  it("auto anchor avoids the corner holding data", () => {
    const base = scene(6);
    const crowdBr: Scene = {
      ...base, bands: [], fits: [], legend: false,
      series: [{ id: "d", label: "d", x: [0, 1, 2, 3, 4, 10, 9.5, 9.5], y: [10, 10, 10, 10, 10, 0, 0.8, 0.8], style: "points" }],
      annotation: { lines: ["a line", "b line"], anchor: "auto" },
    };
    const fixed = computeLayout({ ...crowdBr, annotation: { lines: ["a line", "b line"], anchor: "br" } });
    const auto = computeLayout(crowdBr);
    expect(auto.annotation?.box).not.toEqual(fixed.annotation?.box);
  });
});
