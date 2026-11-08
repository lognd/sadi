// frob:ticket 01M6W7R3KN3HXVMJQ1D3MJNBZY
import { describe, expect, it } from "vitest";
import { sceneToSvg } from "../core";
import { annotationText, buildStressStrainScene } from "./buildScene";
import type { StressStrainData, StressStrainPoint } from "./model";
import { clampWindow, dragWindow, keyStep, nearestIndex, setEdge } from "./selection";

const pts: StressStrainPoint[] = Array.from({ length: 10 }, (_, i) => ({
  index: i, strain: i * 0.001, stress: i < 6 ? 70000 * i * 0.001 : 420 + (i - 6) * 5,
  strainU: 0.00002, stressU: 2,
  settleSource: i === 4 ? "forced_early" : "settled_window", saturated: i === 9,
}));
const data: StressStrainData = {
  points: pts,
  fit: { first: 1, last: 5, modulusMpa: 70000, interceptMpa: 0, eGpa: 70, eU95Gpa: 1.2, r2: 0.9998, lowR2: false },
  yield: { stress: 280, strain: 0.006, offset: 0.002 },
};

describe("window selection", () => {
  it("clamps to bounds and minimum size", () => {
    expect(clampWindow({ first: -3, last: 99 }, 10)).toEqual({ first: 0, last: 9 });
    expect(clampWindow({ first: 4, last: 4 }, 10)).toEqual({ first: 4, last: 6 });
    expect(clampWindow({ first: 0, last: 1 }, 2)).toBeNull();
  });
  it("setEdge pushes the other edge to keep 3 points", () => {
    expect(setEdge({ first: 1, last: 5 }, "first", 4, 10)).toEqual({ first: 4, last: 6 });
    expect(setEdge({ first: 3, last: 6 }, "last", 4, 10)).toEqual({ first: 2, last: 4 });
    expect(setEdge({ first: 1, last: 5 }, "first", 9, 10)).toEqual({ first: 7, last: 9 });
  });
  it("keyboard steps and ignores other keys", () => {
    expect(keyStep({ first: 1, last: 5 }, "last", "ArrowRight", false, 10)).toEqual({ first: 1, last: 6 });
    expect(keyStep({ first: 1, last: 5 }, "last", "ArrowRight", true, 10)).toEqual({ first: 1, last: 9 });
    expect(keyStep({ first: 1, last: 5 }, "first", "Home", false, 10)).toEqual({ first: 0, last: 5 });
    expect(keyStep({ first: 1, last: 5 }, "last", "End", false, 10)).toEqual({ first: 1, last: 9 });
    expect(keyStep({ first: 1, last: 5 }, "last", "a", false, 10)).toBeNull();
  });
  it("drag grabs the nearest edge", () => {
    const s = pts.map((p) => p.strain);
    expect(nearestIndex(s, 0.0071)).toBe(7);
    expect(dragWindow(s, { first: 1, last: 5 }, 0.0071)).toEqual({ window: { first: 1, last: 7 }, edge: "last" });
    expect(dragWindow(s, { first: 1, last: 5 }, 0.0, "first")).toEqual({ window: { first: 0, last: 5 }, edge: "first" });
  });
});

describe("scene mapping", () => {
  const scene = buildStressStrainScene(data);
  it("has window shading, E fit, offset line and yield marker", () => {
    expect(scene.bands?.map((b) => b.id)).toEqual(["window"]);
    expect(scene.fits?.map((f) => f.id)).toEqual(["efit", "offset"]);
    expect(scene.series.find((s) => s.id === "yield")?.x).toEqual([0.006]);
  });
  it("marks forced-early and saturated points distinctly with uncertainty bars", () => {
    expect(scene.series.find((s) => s.id === "forced")?.marker).toBe("ring");
    expect(scene.series.find((s) => s.id === "saturated")?.marker).toBe("cross");
    expect(scene.series.filter((s) => s.id.startsWith("uy-")).length).toBe(10);
    expect(scene.footer).toContain("saturation");
  });
  it("annotates E with uncertainty and r^2", () => {
    expect(annotationText(data)).toBe("E = 70.0 +/- 1.2 GPa, r^2 = 0.9998");
    expect(scene.annotation?.lines).toEqual(["E = 70.0 +/- 1.2 GPa, r^2 = 0.9998"]);
  });
  it("is deterministic and renders to SVG (golden)", () => {
    expect(sceneToSvg(buildStressStrainScene(data))).toMatchSnapshot();
  });
  it("omits fit artefacts without a fit", () => {
    const s = buildStressStrainScene({ ...data, fit: null, yield: null });
    expect(s.fits).toEqual([]);
    expect(s.annotation).toBeUndefined();
  });
});
