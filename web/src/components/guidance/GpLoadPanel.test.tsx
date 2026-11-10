// frob:ticket 01M71KE93DMK963M32SPH83NF4
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { GpLoadPanel, alternativesOf, gpStateNote, kgToNewtons, loadText } from "./GpLoadPanel";
import { GuidancePanel } from "./GuidancePanel";
import type { GuidanceState } from "./types";

const base: GuidanceState = {
  phase: "elastic", next_action: "Add 1.250 kg of masses to the hanger (the hanger is added for you)", suggested_load_kg: 1.25,
  expected_value: 70, unit: "GPa",
  confidence: { quantity: "E", half_width: 4, target_half_width: 3.5, relative: 0.0571, fraction: 0.875, met: false },
  points_taken: 4, max_points: 12, stop_early: false, stop_reason: "",
  proposed_next_phase: null, run_complete_proposed: false,
};
const gp: GuidanceState = {
  ...base, expected_gain: 0.123, expected_half_width: 3.21, alternatives: [1.0, 1.5, 2.0, 2.5], gp_state: "diminishing",
};

describe("GP load panel", () => {
  it("shows load in kg and N, gain, half-width, 3 alternatives and the stop hint", () => {
    const html = renderToString(<GpLoadPanel guidance={gp} onPickLoad={vi.fn()} />);
    expect(html).toContain("1.250 kg (12.26 N)");
    expect(html).toContain("12.3 % narrower");
    expect(html).toContain("3.21 GPa");
    expect(html).toContain("Use alternative load 1.000 kg");
    expect(html).toContain("Use alternative load 2.000 kg");
    expect(html).not.toContain("2.500 kg");
    expect(html).toContain("You may stop early");
  });

  it("falls back to even-schedule text when GP fields are absent", () => {
    const html = renderToString(<GpLoadPanel guidance={base} />);
    expect(html).toContain('data-testid="gp-fallback"');
    expect(html).toContain("Even-schedule suggestion: 1.250 kg");
    expect(html).not.toContain("<button");
    expect(renderToString(<GpLoadPanel guidance={{ ...base, suggested_load_kg: null }} />)).toContain("No load suggestion yet");
  });

  it("shows n/a for missing gain and no buttons without alternatives", () => {
    const html = renderToString(<GpLoadPanel guidance={{ ...gp, expected_gain: null, expected_half_width: null, alternatives: [] }} />);
    expect(html).toContain("n/a");
    expect(html).not.toContain("<button");
  });

  it("helpers convert and filter", () => {
    expect(kgToNewtons(1)).toBeCloseTo(9.80665);
    expect(loadText(1)).toBe("1.000 kg (9.81 N)");
    expect(alternativesOf({ ...gp, alternatives: [NaN, 1, 2, 3, 4] })).toEqual([1, 2, 3]);
    expect(gpStateNote("unreliable")).toContain("unreliable");
    expect(gpStateNote("")).toBe("");
  });

  it("is embedded in the guidance panel, with loading and error states", () => {
    expect(renderToString(<GuidancePanel guidance={gp} />)).toContain('data-testid="gp-panel"');
    expect(renderToString(<GuidancePanel guidance={base} />)).toContain('data-testid="gp-fallback"');
    expect(renderToString(<GuidancePanel guidance={null} status="loading" />)).toContain("Loading guidance");
    expect(renderToString(<GuidancePanel guidance={null} status="error" error="no session" />)).toContain("Guidance unavailable: no session");
  });
});
