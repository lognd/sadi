// frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString as rts } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { getDesignAdvice, indicatorText, loadText, type DesignAdvice, type DesignIndicator } from "./designAdvice";
import { SuggestedWeightView } from "./SuggestedWeightPanel";

const ind = (o: Partial<DesignIndicator>): DesignIndicator => ({ n: 4, state: "collecting", ratio: 1.2, consecutive_ok: 0, patience: 2, reasons: [], ...o });
const advice: DesignAdvice = {
  suggestion: { x: 2.5, unit: "kg", expected_gain: 0.01, why: "This load should tighten the result the most.", alternatives: [{ candidate_id: "m1", x: 5, expected_gain: 0.009 }] },
  indicator: ind({ state: "enough", consecutive_ok: 2 }),
};

describe("suggested weight", () => {
  it("shows load in kg and N, why, alternatives and the indicator", () => {
    const h = rts(<SuggestedWeightView advice={advice} />).replaceAll("<!-- -->", "");
    expect(h).toContain("Suggested next weight");
    expect(h).toContain("2.50 kg (24.5 N)");
    expect(h).toContain("tighten the result");
    expect(h).toContain("5.00 kg");
    expect(h).toContain("Enough data");
    expect(h).toContain("You decide");
  });
  it("reads cold start in plain language", () => {
    expect(indicatorText(ind({ n: 1, state: "unreliable", reasons: ["cold_start"] }))).toContain("collect a few more points");
  });
  it("shows an unavailable note on failure", () => {
    expect(rts(<SuggestedWeightView advice={null} failed />)).toContain("unavailable");
  });
  it("formats heights without newtons", () => {
    expect(loadText(0.01, "m")).toBe("0.0100 m");
  });
  it("fetches the read-only route", async () => {
    let url = "";
    const f = ((u: string) => { url = u; return Promise.resolve(new Response(JSON.stringify(advice), { status: 200, headers: { "Content-Type": "application/json" } })); }) as unknown as typeof fetch;
    const r = await getDesignAdvice("elastic", f);
    expect(r.ok).toBe(true);
    expect(url).toContain("/api/design/next-weight?phase=elastic");
  });
});
