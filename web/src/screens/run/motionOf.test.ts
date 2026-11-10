import { describe, expect, it } from "vitest";
import { motionOf } from "./live";

describe("motionOf", () => {
  it("reports loading (no load or too few samples) as unknown, not creeping", () => {
    expect(motionOf("loading")).toBe("unknown");
    expect(motionOf(null)).toBe("unknown");
  });
  it("maps creeping and settled directly", () => {
    expect(motionOf("creeping")).toBe("creeping");
    expect(motionOf("settled")).toBe("settled");
  });
});
