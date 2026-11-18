// frob:ticket 01M72Y6ZXN756YB93HK0H3ACB5
import { describe, expect, it } from "vitest";
import { DEFAULT_SIDE, MAX_SIDE, MIN_SIDE, squareSide } from "./useContainerSquare";

describe("squareSide", () => {
  it("clamps to 0.6*viewport height at 1024x768", () => {
    expect(squareSide(984, 768)).toBe(460);
  });
  it("clamps to MAX_SIDE on tall viewports", () => {
    expect(squareSide(2000, 2000)).toBe(MAX_SIDE);
  });
  it("uses container width when smallest", () => {
    expect(squareSide(300, 1000)).toBe(300);
  });
  it("never goes below MIN_SIDE", () => {
    expect(squareSide(100, 300)).toBe(MIN_SIDE);
  });
  it("falls back to default for bad width and ignores bad height", () => {
    expect(squareSide(0, 768)).toBe(DEFAULT_SIDE);
    expect(squareSide(400, Number.NaN)).toBe(400);
  });
});
