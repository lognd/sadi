// frob:ticket 01M6W7RAPKVH796SZ6Z9EFDXQE
// frob:accept COV001
import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import {
  ADVANCE_KEY, GuidancePanel, advanceLabel, expectedText, handleAdvanceKey, meterPercent,
  nextStepText, parseTargetPercent,
} from "./GuidancePanel";
import { getGuidance, guidanceUrl } from "./api";
import type { GuidanceState } from "./types";

const base: GuidanceState = {
  phase: "elastic", next_action: "Use weights 3, 5, 6", suggested_load_kg: 1.25,
  expected_value: 70, unit: "GPa",
  confidence: { quantity: "E", half_width: 4, target_half_width: 3.5, relative: 0.0571, fraction: 0.875, met: false },
  points_taken: 4, max_points: 12, stop_early: false, stop_reason: "",
  proposed_next_phase: null, run_complete_proposed: false,
};
const stop: GuidanceState = {
  ...base, stop_early: true, stop_reason: "E half-width is within the 5.0% target.",
  proposed_next_phase: "plastic", confidence: { ...base.confidence, fraction: 1, met: true },
};
const key = (k: string) => ({ key: k, ctrlKey: false, metaKey: false, altKey: false });

describe("guidance panel", () => {
  it("shows next step, expected value and an accessible meter", () => {
    const html = renderToString(<GuidancePanel guidance={base} />);
    expect(html).toContain("Use weights 3, 5, 6 (1.250 kg)");
    expect(html).toContain("Expected E: 70 GPa");
    expect(html).toContain('role="meter"');
    expect(html).toContain('aria-valuenow="88"');
    expect(html).toContain('aria-valuemin="0"');
    expect(html).toContain('aria-valuemax="100"');
    expect(html).not.toContain("stop-early");
  });

  it("shows the target as an editable percentage", () => {
    expect(renderToString(<GuidancePanel guidance={base} target={0.1} />)).toContain('value="10"');
  });

  it("shows the advisory banner with an advance button only when a handler is given", () => {
    const withBtn = renderToString(<GuidancePanel guidance={stop} onAdvance={() => undefined} />);
    expect(withBtn).toContain('data-testid="stop-early"');
    expect(withBtn).toContain("You may keep going");
    expect(withBtn).toContain("Move to plastic phase (N)");
    expect(withBtn).toContain("Confidence is enough");
    expect(renderToString(<GuidancePanel guidance={stop} />)).not.toContain("<button");
  });

  it("renders an empty state", () => {
    expect(renderToString(<GuidancePanel guidance={null} />)).toContain("No guidance yet");
  });

  it("advances only on the plain advance key while a proposal shows", () => {
    const on = vi.fn();
    expect(handleAdvanceKey(key("x"), stop, on)).toBe(false);
    expect(handleAdvanceKey({ ...key("n"), ctrlKey: true }, stop, on)).toBe(false);
    expect(handleAdvanceKey(key("n"), base, on)).toBe(false);
    expect(handleAdvanceKey(key("n"), stop, undefined)).toBe(false);
    expect(on).not.toHaveBeenCalled();
    expect(handleAdvanceKey(key(ADVANCE_KEY.toUpperCase()), stop, on)).toBe(true);
    expect(on).toHaveBeenCalledTimes(1);
  });

  it("derives text and values", () => {
    expect(nextStepText({ ...base, suggested_load_kg: null })).toBe("Use weights 3, 5, 6");
    expect(expectedText({ ...base, expected_value: null })).toBeNull();
    expect(meterPercent({ ...base, confidence: { ...base.confidence, fraction: 2 } })).toBe(100);
    expect(parseTargetPercent("5")).toBe(0.05);
    expect(parseTargetPercent("0")).toBeNull();
    expect(parseTargetPercent("abc")).toBeNull();
    expect(advanceLabel(null)).toBe("Finish run");
  });
});

describe("guidance api", () => {
  it("builds the query string", () => {
    expect(guidanceUrl({})).toBe("/api/results/guidance");
    expect(guidanceUrl({ phase: "elastic", hold: "ready", target: 0.05 }))
      .toBe("/api/results/guidance?phase=elastic&hold=ready&target=0.05");
  });

  it("returns the payload via the injected fetcher", async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify(base), { status: 200 }));
    const r = await getGuidance({ phase: "elastic" }, f);
    expect(r.ok && r.value.next_action).toBe("Use weights 3, 5, 6");
  });

  it("returns an http error Result on 409", async () => {
    const f = vi.fn().mockResolvedValue(new Response("no session", { status: 409 }));
    const r = await getGuidance({}, f);
    expect(!r.ok && r.error.kind === "http").toBe(true);
  });
});
