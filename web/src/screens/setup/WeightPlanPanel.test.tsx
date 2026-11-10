// frob:ticket 01M72X7ZB936PEBXHRGX06FSAD
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EMPTY_FORM, savedText, PlanResult, WeightPlanPanel, parsePlanForm, type PlanReply } from "./WeightPlanPanel";

describe("parsePlanForm", () => {
  it("converts newtons to kg and mm to SI and leaves slope unset", () => {
    const r = parsePlanForm({ ...EMPTY_FORM, weights: "9.80665 0.0980665\n19.6133" });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.value.weights[0]?.mass_kg).toBeCloseTo(1);
      expect(r.value.weights[0]?.u_mass_kg).toBeCloseTo(0.01);
      expect(r.value.weights[1]?.mass_kg).toBeCloseTo(2);
      expect(r.value.length_m).toBeCloseTo(0.08313);
      expect(r.value.cal_slope_v_per_m).toBeUndefined();
    }
  });
  it("sends an entered slope and rejects bad input with a sentence", () => {
    const ok = parsePlanForm({ ...EMPTY_FORM, weights: "5", slope: "200" });
    expect(ok.ok && ok.value.cal_slope_v_per_m).toBe(200);
    expect(parsePlanForm({ ...EMPTY_FORM, weights: "" }).ok).toBe(false);
    expect(parsePlanForm({ ...EMPTY_FORM, weights: "abc" }).ok).toBe(false);
    expect(parsePlanForm({ ...EMPTY_FORM, weights: "5", slope: "0" }).ok).toBe(false);
  });
});

describe("savedText", () => {
  it("distinguishes a new version from an identical re-save", () => {
    expect(savedText({ seq: 5, appended: true, events: 2 })).toContain("version 2");
    expect(savedText({ seq: null, appended: false, events: 2 })).toContain("nothing new");
  });
});

describe("views", () => {
  it("renders the ordered hangs with plus/minus", () => {
    const reply: PlanReply = {
      plan: { phase: "elastic", n_usable: 3, dropped_capacity: 1, dropped_saturation: 0, hangs: [{ order: 1, weight_ids: ["w1", "w2"], total_mass_kg: 0.03, u_mass_kg: 0.0001, tension_n: 0.29, predicted_volts: 0.01, reason: "Hang #1: lightest" }] },
      cal_slope_v_per_m: 200, cal_source: "entered", propagated: null, propagation_note: "Uncertainty is shown for the elastic plan only.",
    };
    const html = renderToString(<PlanResult reply={reply} />);
    expect(html).toContain("w1 + w2");
    expect(html).toContain("+/-");
    expect(html).toContain("break the wire");
  });
  it("renders the form without a lab", () => {
    expect(renderToString(<WeightPlanPanel />)).toContain("needs no lab connection");
  });
});
