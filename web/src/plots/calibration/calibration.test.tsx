// frob:ticket 01M6W7R3D3KT3NM6JETDDAPA9P
import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import { sceneToSvg } from "../core";
import { CalibrationPlot } from "./CalibrationPlot";
import { buildCalibrationScenes } from "./scenes";
import type { CalibrationData } from "./types";

const volts = [0, 1, 2, 3, 4];
const data = (extra: Partial<CalibrationData> = {}): CalibrationData => ({
  volts,
  height: volts.map((v) => 10 * v + 1),
  height_u95: volts.map(() => 0.2),
  fit_volts: [0, 4],
  fit_height: [1, 41],
  band_lower: [0.8, 40.7],
  band_upper: [1.2, 41.3],
  residuals: [0.01, -0.02, 0.0, 0.02, -0.01],
  equation: "h = (10.00 +/- 0.12) V + (1.00 +/- 0.30)",
  r2: "r^2 = 0.9998",
  ...extra,
});

describe("calibration scenes", () => {
  it("maps points, error bars, fit, band and annotation (acceptance 1)", () => {
    const r = buildCalibrationScenes(data());
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    const { main, residuals } = r.value;
    expect(main.series).toHaveLength(1);
    expect(main.series[0]?.yErr).toEqual(data().height_u95);
    expect(main.annotation?.anchor).toBe("auto");
    expect(main.bands).toHaveLength(1);
    expect(main.fits).toHaveLength(1);
    expect(main.annotation?.lines[0]).toBe("h = (10.00 +/- 0.12) V + (1.00 +/- 0.30)");
    expect(main.annotation?.lines).toContain("r^2 = 0.9998");
    expect(residuals.series[0]?.y).toEqual(data().residuals);
    expect(main.xAxis.min).toBe(residuals.xAxis.min);
    expect(main.xAxis.max).toBe(residuals.xAxis.max);
    const svg = sceneToSvg(main);
    expect(svg).toContain("+/- 0.12");
  });

  it("rejects bad payloads without throwing", () => {
    expect(buildCalibrationScenes(data({ volts: [], height: [], residuals: [] }))).toEqual({ ok: false, error: { kind: "empty" } });
    const mism = buildCalibrationScenes(data({ residuals: [0] }));
    expect(!mism.ok && mism.error.kind).toBe("length_mismatch");
    const nf = buildCalibrationScenes(data({ height: [0, 1, Number.NaN, 3, 4] }));
    expect(!nf.ok && nf.error.kind).toBe("non_finite");
    const mt = buildCalibrationScenes(data({ equation: " " }));
    expect(!mt.ok && mt.error.kind).toBe("missing_text");
  });
});

describe("calibration live update and golden", () => {
  it("scene changes after each captured point (acceptance 2)", () => {
    const a = buildCalibrationScenes(data());
    const more = data({
      volts: [...volts, 5], height: [...data().height, 51], height_u95: [...volts.map(() => 0.2), 0.2],
      residuals: [...data().residuals, 0.01],
    });
    const b = buildCalibrationScenes(more);
    if (!a.ok || !b.ok) throw new Error("expected ok");
    expect(sceneToSvg(a.value.main)).not.toBe(sceneToSvg(b.value.main));
    expect(b.value.main.annotation?.lines).toContain("n = 6");
  });

  it("matches the golden SVG for both panels", () => {
    const r = buildCalibrationScenes(data());
    if (!r.ok) throw new Error("expected ok");
    expect(sceneToSvg(r.value.main)).toMatchSnapshot("main");
    expect(sceneToSvg(r.value.residuals)).toMatchSnapshot("residuals");
  });

  it("component renders both canvases, or a status when empty", () => {
    const html = renderToString(<CalibrationPlot data={data()} />);
    expect(html).toContain("calibration-main");
    expect(html).toContain("calibration-residuals");
    expect(renderToString(<CalibrationPlot data={data({ volts: [], height: [], residuals: [] })} />)).toContain("calibration-empty");
  });
});
