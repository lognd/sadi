// frob:ticket 01M6XB9EBAP0ZTTYAMG9NEG3KJ
import { describe, expect, test } from "vitest";
import { contrastRatio, parseHex } from "../a11y/contrast";
import { MARKER_CYCLE, seriesCue } from "./core/scene";
import type { Series } from "./core/scene";
import { lightTheme } from "./theme";

type M = readonly [readonly [number, number, number], readonly [number, number, number], readonly [number, number, number]];
// Vienot/Brettel-style linear-RGB simulation matrices (Machado 2009, severity 1.0).
const DEUTAN: M = [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]];
const PROTAN: M = [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]];

const lin = (c: number): number => { const s = c / 255; return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };

function simulate(hex: string, m: M): [number, number, number] {
  const v = parseHex(hex).map(lin) as [number, number, number];
  return m.map((r) => Math.min(1, Math.max(0, r[0] * v[0] + r[1] * v[1] + r[2] * v[2]))) as [number, number, number];
}

function lab(rgb: [number, number, number]): [number, number, number] {
  const [r, g, b] = rgb;
  const x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
  const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const f = (t: number): number => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
}

const deltaE = (a: string, b: string, m: M): number => {
  const p = lab(simulate(a, m));
  const q = lab(simulate(b, m));
  return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
};

describe("plot palette accessibility", () => {
  const pal = lightTheme.palette;

  test.each(pal.map((c) => [c]))("%s has >= 3:1 against plot background", (c) => {
    expect(contrastRatio(c, lightTheme.plotBackground)).toBeGreaterThanOrEqual(3);
  });

  test("series distinguishable under deuteranopia/protanopia, or carry distinct cues", () => {
    const THRESHOLD = 10; // CIE76 deltaE
    const cues = pal.map((_, i) => seriesCue({} as Series, i));
    for (const [name, m] of [["deuteranopia", DEUTAN], ["protanopia", PROTAN]] as const) {
      for (let i = 0; i < pal.length; i++) {
        for (let j = i + 1; j < pal.length; j++) {
          const de = deltaE(pal[i] as string, pal[j] as string, m);
          const cueDiffers = cues[i]?.marker !== cues[j]?.marker || cues[i]?.dashed !== cues[j]?.dashed;
          if (de < THRESHOLD) expect(cueDiffers, `${name} ${String(i)}/${String(j)} deltaE ${de.toFixed(1)}`).toBe(true);
        }
      }
    }
  });

  test("adjacent series always differ in non-colour cue", () => {
    for (let i = 0; i < 12; i++) {
      const a = seriesCue({} as Series, i);
      const b = seriesCue({} as Series, i + 1);
      expect(a.marker !== b.marker || a.dashed !== b.dashed).toBe(true);
    }
    expect(MARKER_CYCLE.length).toBeGreaterThanOrEqual(3);
  });

  test("explicit series style overrides the cue", () => {
    expect(seriesCue({ marker: "cross", dashed: false } as Series, 1)).toEqual({ marker: "cross", dashed: false });
  });
});
