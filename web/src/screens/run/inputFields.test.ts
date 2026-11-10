// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
// frob:ticket 01M6X241EV9Z0JS4TCJPQBZCCN
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { capturedMessage } from "./capture";
import { PHASE_FIELDS, collectInputs, plausibilityNote, splitSpecimen } from "./inputFields";

/** Unwrap a fixture lookup; a miss is a test bug. */
function required<T>(v: T | undefined): T {
  if (v === undefined) throw new Error("fixture field missing");
  return v;
}

describe("collectInputs", () => {
  it("calibration: live volts when blank, typed height in SI", () => {
    const r = collectInputs("calibrate", { height: "0.0125" }, 1.5);
    expect(r).toEqual({ ok: true, value: { volts: 1.5, height: 0.0125 } });
  });
  it("typed volts override the live reading", () => {
    expect(collectInputs("calibrate", { volts: "2", height: "0.01" }, 1.5)).toEqual({ ok: true, value: { volts: 2, height: 0.01 } });
  });
  // regression test for audit1#25 tare n and sd are derived, not typed
  it("tare without live statistics reports the derived fields, none defaulted", () => {
    const r = collectInputs("tare", {}, 1);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.join(" ")).toContain("not enough live readings");
  });
  it("tare takes mean, n and sd from the live statistics and hides n and sd", () => {
    const r = collectInputs("tare", { diameter: "0.0006" }, 9, { mean: 0.5, sd: 0.01, n: 40 });
    expect(r).toEqual({ ok: true, value: { mean: 0.5, n: 40, sd: 0.01, diameter: 0.0006 } });
    expect(PHASE_FIELDS.tare.filter((f) => f.derived === true).map((f) => f.key)).toEqual(["n", "sd"]);
  });
  it("rejects non-numbers and negatives", () => {
    const r = collectInputs("tare", { diameter: "-1", mean: "abc" }, 1, { mean: 0, sd: 0, n: 5 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toHaveLength(2);
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

// regression test for audit1#6 UI half: unit shown and implausible diameter warned with an mm suggestion
describe("plausibilityNote", () => {
  const dia = required(PHASE_FIELDS.tare.find((f) => f.key === "diameter"));
  it("is silent for a plausible wire diameter and blanks", () => {
    expect(plausibilityNote(dia, "0.0006")).toBeNull();
    expect(plausibilityNote(dia, "")).toBeNull();
  });
  it("offers millimetres converted to metres", () => {
    const n = plausibilityNote(dia, "0.6");
    expect(n?.suggest).toBe("0.0006");
    expect(n?.message).toContain("millimetres");
  });
  it("warns without a suggestion when no conversion fits", () => {
    const n = plausibilityNote(dia, "1e-9");
    expect(n).not.toBeNull();
    expect(n?.suggest).toBeNull();
  });
});

describe("user-facing wording (audit1 #15 #32)", () => {
  it("mass label explains in helper text that the hanger is added for you", () => {
    for (const ph of ["elastic", "plastic"] as const) {
      const f = PHASE_FIELDS[ph].find((x) => x.key === "mass_kg");
      expect(f?.label).not.toContain("hanger");
      expect(f?.help).toContain("hanger is added for you");
    }
  });
  it("captured message hides raw uuids", () => {
    const m = capturedMessage("captured 123e4567-e89b-12d3-a456-426614174000");
    expect(m).toBe("Captured.");
    expect(m).not.toMatch(/[0-9a-f]{8}-/);
    expect(capturedMessage("captured p1 123e4567-e89b-12d3-a456-426614174000")).toBe("Captured: captured p1");
  });
});

// frob:ticket 01M7230XMB52H0AA8ETNQ8RBPX
describe("unit-slip ranges and required diameter (audit2 H3/H4)", () => {
  const field = (ph: "calibrate" | "elastic", k: string) => required(PHASE_FIELDS[ph].find((f) => f.key === k));
  it("1 typed for a 1 mm block suggests millimetres", () => {
    const n = plausibilityNote(field("calibrate", "height"), "1");
    expect(n?.suggest).toBe("0.001");
    expect(n?.message).toContain("millimetres");
  });
  it("500 typed for 500 g suggests grams as kg", () => {
    const n = plausibilityNote(field("elastic", "mass_kg"), "500");
    expect(n?.suggest).toBe("0.5");
    expect(n?.message).toContain("grams");
  });
  it("blank diameter is an error on the tare step", () => {
    const r = collectInputs("tare", { mean: "0.1" }, 1, { mean: 0, sd: 0, n: 5 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.join(" ")).toContain("Specimen diameter is required");
  });
});
