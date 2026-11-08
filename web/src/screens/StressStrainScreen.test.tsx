// frob:ticket 01M6WMGMJE0WEXXNQ3AD754A8M
import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import { applyRefit, StressStrainScreen } from "./StressStrainScreen";
import type { StressStrainData } from "../plots/stressstrain/model";

const data: StressStrainData = {
  points: Array.from({ length: 6 }, (_, i) => ({
    index: i, strain: i * 0.001, stress: 70 * i, strainU: 0, stressU: 1, settleSource: "settled_window", saturated: false,
  })),
  fit: { first: 0, last: 4, modulusMpa: 70000, interceptMpa: 0, eGpa: 70, eU95Gpa: 1, r2: 0.999, lowR2: false },
  yield: null,
};
const newFit = { first: 1, last: 5, modulusMpa: 69000, interceptMpa: 1, eGpa: 69, eU95Gpa: 0.5, r2: 0.9995, lowR2: false };

describe("applyRefit", () => {
  it("swaps in the refit E, r^2 and uncertainty and keeps all points", async () => {
    const f: typeof fetch = () => Promise.resolve(new Response(JSON.stringify(newFit)));
    const o = await applyRefit(data, { first: 1, last: 5 }, f);
    expect(o.error).toBeNull();
    expect(o.data.fit).toMatchObject({ first: 1, last: 5, eGpa: 69, eU95Gpa: 0.5, r2: 0.9995 });
    expect(o.data.points).toBe(data.points);
  });

  it("keeps the previous fit and reports the error on failure", async () => {
    const o = await applyRefit(data, { first: 1, last: 5 }, () => Promise.resolve(new Response("nope", { status: 500 })));
    expect(o.data).toBe(data);
    expect(o.error).toContain("HTTP 500");
    const n = await applyRefit(data, { first: 1, last: 5 }, () => Promise.reject(new Error("down")));
    expect(n.data).toBe(data);
    expect(n.error).toContain("down");
  });
});

describe("StressStrainScreen", () => {
  it("renders the plot and the current fit summary", () => {
    const html = renderToString(<StressStrainScreen initial={data} />);
    expect(html).toContain("E = 70.00");
    expect(html).toContain("r^2 = 0.9990");
  });
});
