// frob:ticket 01M71KE5ENACTPQ56XAWW37VH5
import { describe, expect, it } from "vitest";
import { otherTheme, parseTheme, resolveTheme } from "./theme";

describe("theme helpers", () => {
  it("parses only known values", () => {
    expect(parseTheme("dark")).toBe("dark");
    expect(parseTheme("light")).toBe("light");
    expect(parseTheme("blue")).toBeNull();
    expect(parseTheme(null)).toBeNull();
  });
  it("manual choice beats OS preference", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme(null, true)).toBe("dark");
    expect(resolveTheme(null, false)).toBe("light");
  });
  it("toggles", () => {
    expect(otherTheme("dark")).toBe("light");
    expect(otherTheme("light")).toBe("dark");
  });
});
