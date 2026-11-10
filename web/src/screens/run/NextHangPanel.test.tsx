// frob:ticket 01M72YENT6PZMVDMYGZ2BWDNK9
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { NextHangPanel, NextHangView, type NextHangReply } from "./NextHangPanel";

const hang = { order: 1, weight_ids: ["w4", "w5"], total_mass_kg: 0.1, u_mass_kg: 0.0001, tension_n: 0.98, predicted_volts: 0.02, reason: "Hang #1: biggest gain" };
const reply: NextHangReply = {
  captured: 2, next_hang: hang,
  reply: { plan: { phase: "elastic", n_usable: 3, dropped_capacity: 0, dropped_saturation: 0, hangs: [hang] }, cal_slope_v_per_m: 200, cal_source: "entered", propagated: null, propagation_note: "" },
};

describe("NextHangView", () => {
  it("shows the next hang, why, and how many captured", () => {
    const html = renderToString(<NextHangView state={{ kind: "ready", value: reply }} />);
    expect(html).toContain("w4 + w5");
    expect(html).toContain("biggest gain");
    expect(html).toContain("replanned from");
  });
  it("says so when the plan is finished", () => {
    const html = renderToString(<NextHangView state={{ kind: "ready", value: { ...reply, next_hang: null } }} />);
    expect(html).toContain("No further hang");
  });
  it("explains the empty and failed states", () => {
    expect(renderToString(<NextHangView state={{ kind: "none" }} />)).toContain("Save them from the Weight plan");
    expect(renderToString(<NextHangView state={{ kind: "failed" }} />)).toContain("unavailable");
  });
  it("starts in the loading state", () => {
    expect(renderToString(<NextHangPanel tick={0} />)).toContain("Loading plan");
  });
});
