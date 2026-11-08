// frob:ticket 01M6W7R3EPVRGG4R93B7WJVKMW
import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import { sceneToSvg, validateScene, figureScenes } from "../core";
import { CreepPlot } from "./CreepPlot";
import { buildCreepScene } from "./scene";
import type { CreepData } from "./types";

const t = [1, 2, 5, 10, 20, 50, 100, 200];
const creeping = (id: string, label: string, b: number, slips: CreepData["holds"][number]["slips"] = []) => ({
  id, label, t,
  strain: t.map((x) => 1e-4 + b * Math.log(x) + (slips.length > 0 && x >= 50 ? 3e-5 : 0)),
  fit: { a: 1e-4, b, b_se: b / 50, r2: 0.9991 },
  slips,
  settle_band: { lower: 1.5e-4, upper: 2.5e-4 },
});
const data = (): CreepData => ({
  holds: [creeping("h1", "10 kN", 2e-5), creeping("h2", "20 kN", 4e-5, [{ t: 50, strain: 2.9e-4, size_mm: 0.012 }])],
});

describe("creep figure", () => {
  it("one panel per hold on a log x axis with fit, slips and settle band (acceptance 1)", () => {
    const r = buildCreepScene(data());
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    const fig = r.value;
    expect(fig.xAxis.scale).toBe("log");
    expect(fig.panels).toHaveLength(2);
    expect(fig.panels[0]?.fits).toHaveLength(1);
    expect(fig.panels[0]?.annotation?.lines[0]).toContain("ln(t)");
    expect(fig.panels[0]?.spans).toHaveLength(1);
    expect(fig.panels[0]?.markers).toHaveLength(0);
    expect(fig.panels[1]?.markers?.[0]?.label).toBe("slip 0.012 mm");
    expect(fig.panels[1]?.markers?.[0]?.kind).toBe("cross");
    for (const s of figureScenes(fig)) expect(validateScene(s).ok).toBe(true);
  });

  it("rejects bad payloads without throwing", () => {
    expect(buildCreepScene({ holds: [] })).toEqual({ ok: false, error: { kind: "empty" } });
    const h = creeping("h", "x", 1e-5);
    const mism = buildCreepScene({ holds: [{ ...h, strain: [1] }] });
    expect(!mism.ok && mism.error.kind).toBe("length_mismatch");
    const nf = buildCreepScene({ holds: [{ ...h, strain: h.strain.map(() => Number.NaN) }] });
    expect(!nf.ok && nf.error.kind).toBe("non_finite");
    const np = buildCreepScene({ holds: [{ ...h, t: h.t.map((x) => x - 1) }] });
    expect(!np.ok && np.error.kind).toBe("non_positive_time");
  });

  it("a hold without a fit says so and draws no fit line", () => {
    const r = buildCreepScene({ holds: [{ ...creeping("h", "x", 1e-5), fit: null }] });
    if (!r.ok) throw new Error("expected ok");
    expect(r.value.panels[0]?.fits).toBeUndefined();
    expect(r.value.panels[0]?.annotation?.lines[0]).toContain("no fit");
  });
});

describe("creep golden and component", () => {
  it("matches the golden SVG for creeping and slipping holds (acceptance 2)", () => {
    const r = buildCreepScene(data());
    if (!r.ok) throw new Error("expected ok");
    const svg = sceneToSvg(r.value);
    expect(svg).toContain("slip 0.012 mm");
    expect(svg).toMatchSnapshot("creep");
  });

  it("component renders a canvas, or a status when empty", () => {
    expect(renderToString(<CreepPlot data={data()} />)).toContain("creep-plot");
    expect(renderToString(<CreepPlot data={{ holds: [] }} />)).toContain("creep-empty");
  });
});
