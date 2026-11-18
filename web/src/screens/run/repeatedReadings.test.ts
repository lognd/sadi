// frob:ticket 01M72YKF3EN8RJX7RCH78JDPQC
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { parseReadings, summarizeReadings, t95 } from "./repeatedReadings";

describe("repeated readings", () => {
  it("parses comma, space and newline separated numbers", () => {
    expect(parseReadings("1, 2\n3 4")).toEqual({ ok: true, value: [1, 2, 3, 4] });
  });
  it("names a bad token", () => {
    const r = parseReadings("1 x");
    expect(r.ok).toBe(false);
  });
  it("RSS of t*s/sqrt(n) and instrument U", () => {
    const r = summarizeReadings([1, 2, 3], 0.5);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.value.mean).toBe(2);
      expect(r.value.sd).toBeCloseTo(1, 12);
      const typeA = (t95(2) * 1) / Math.sqrt(3);
      expect(r.value.u95).toBeCloseTo(Math.sqrt(typeA ** 2 + 0.25), 12);
    }
  });
  it("a single reading has only the instrument term", () => {
    const r = summarizeReadings([5], 0.2);
    expect(r).toEqual({ ok: true, value: { n: 1, mean: 5, sd: 0, u95: 0.2 } });
  });
  it("rejects negative instrument uncertainty", () => {
    expect(summarizeReadings([1, 2], -1).ok).toBe(false);
  });
});
