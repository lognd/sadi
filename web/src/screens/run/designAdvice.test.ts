// frob:ticket 01M72YPB58KPZ9WR5BE2Q852YF
import { describe, expect, it } from "vitest";
import { indicatorText, type DesignIndicator } from "./designAdvice";

const base: DesignIndicator = { n: 5, state: "collecting", ratio: null, consecutive_ok: 0, patience: 3, reasons: [] };

describe("indicatorText range_exhausted", () => {
  it("says the top of the elastic range is reached", () => {
    const t = indicatorText({ ...base, reasons: ["range_exhausted"] });
    expect(t).toContain("top of the elastic range");
  });
});

// frob:ticket 01M72YKEYW6QFR5YTFSV2YBKMJ
describe("indicatorText new reasons", () => {
  it("explains singular and no_offset instead of the generic line", () => {
    expect(indicatorText({ ...base, reasons: ["singular"] })).toContain("cannot be fitted");
    expect(indicatorText({ ...base, reasons: ["no_offset"] })).toContain("yield offset");
  });
  it("falls back to state wording for diminishing_returns", () => {
    expect(indicatorText({ ...base, state: "diminishing", reasons: ["diminishing_returns"] })).toContain("Nearly there");
  });
});
