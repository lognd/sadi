// frob:ticket 01M6X241EV9Z0JS4TCJPQBZCCN
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { collectInputs, splitSpecimen } from "./inputFields";

describe("collectInputs", () => {
  it("calibration: live volts when blank, typed height in SI", () => {
    const r = collectInputs("calibrate", { height: "0.0125" }, 1.5);
    expect(r).toEqual({ ok: true, value: { volts: 1.5, height: 0.0125 } });
  });
  it("typed volts override the live reading", () => {
    expect(collectInputs("calibrate", { volts: "2", height: "0.01" }, 1.5)).toEqual({ ok: true, value: { volts: 2, height: 0.01 } });
  });
  it("missing required values are reported, none defaulted", () => {
    const r = collectInputs("tare", {}, 1);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.join(" ")).toContain("Sample count n is required");
  });
  it("rejects non-numbers, fractions for n and negatives", () => {
    const r = collectInputs("tare", { n: "2.5", sd: "-1", mean: "abc" }, 1);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toHaveLength(3);
  });
  it("load phases send mass_kg and omit blank optionals", () => {
    expect(collectInputs("elastic", { mass_kg: "0.2" }, 0.7)).toEqual({ ok: true, value: { volts: 0.7, mass_kg: 0.2 } });
  });
  it("no live reading and no typed volts is an error", () => {
    expect(collectInputs("plastic", { mass_kg: "0.2" }, null).ok).toBe(false);
  });
});

// frob:ticket 01M6X6PW1F4HNNFMMY5YV3QKP9
describe("splitSpecimen", () => {
  it("separates specimen geometry from the tare point's own inputs", () => {
    const r = splitSpecimen("tare", { n: 100, diameter: 0.006, hanger_kg: 0.05 });
    expect(r.own).toEqual({ n: 100 });
    expect(r.specimen).toEqual({ diameter: 0.006, hanger_kg: 0.05 });
  });
  it("returns no specimen point without a diameter", () => {
    expect(splitSpecimen("tare", { n: 100 }).specimen).toBeNull();
  });
});
