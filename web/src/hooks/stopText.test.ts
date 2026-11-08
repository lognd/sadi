// frob:ticket 01M6XAASH92DG6W6GDJBJVWSNR
import { describe, expect, it } from "vitest";
import { stopText } from "./stopText";

describe("stopText", () => {
  it("explains a device fault with zero points and says what to do", () => {
    const t = stopText("device_fault", "Check the device connection; saved data is safe", null);
    expect(t).not.toContain("device_fault");
    expect(t).toContain("Doctor");
    expect(t).toContain("capture a point first");
  });
  it("omits the zero-point advice once a point exists", () => {
    expect(stopText("device_fault", "", 3)).not.toContain("capture a point first");
  });
  it("falls back to the server hint for unknown reasons", () => {
    expect(stopText("odd", "do x", 1)).toBe("The run stopped (odd). do x");
  });
});
