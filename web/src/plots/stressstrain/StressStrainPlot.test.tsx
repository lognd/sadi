// frob:ticket 01M6W7R3KN3HXVMJQ1D3MJNBZY
import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import { StressStrainPlot } from "./StressStrainPlot";
import type { StressStrainData } from "./model";

const data: StressStrainData = {
  points: Array.from({ length: 6 }, (_, i) => ({
    index: i, strain: i * 0.001, stress: 70 * i, strainU: 0, stressU: 1, settleSource: "settled_window", saturated: false,
  })),
  fit: { first: 0, last: 4, modulusMpa: 70000, interceptMpa: 0, eGpa: 70, eU95Gpa: 1, r2: 0.999, lowR2: false },
  yield: null,
};

describe("StressStrainPlot", () => {
  it("renders an accessible group with window controls", () => {
    const html = renderToString(<StressStrainPlot data={data} onWindowChange={() => undefined} />);
    expect(html).toContain('role="group"');
    expect(html).toContain("Window start");
    expect(html).toContain("to <!-- -->4");
  });
});
