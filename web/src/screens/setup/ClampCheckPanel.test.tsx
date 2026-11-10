// frob:ticket 01M6XA21KQE5WEXAN39683H4S9
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ClampCheckPanel, ClampCheckView, apiErrorText } from "./ClampCheckPanel";
import { cycleBody, parseCycle, type ClampStatus } from "./clampApi";

const status = (passed: boolean | null): ClampStatus => ({
  guidance: "Apply about 10% of the test load.", required: 3, return_tol: 2e-5, passed,
  advice: passed === false ? "Re-tighten clamps" : passed ? "Proceed" : "",
  cycles: [{ index: 0, zero_shift: 1e-6, slip_events: 0, returned: true, passed: true }],
});

describe("parseCycle", () => {
  it("parses numbers and defaults slips to 0", () => {
    const r = parseCycle({ zeroBefore: "0", zeroAfter: "1e-6", slips: "" });
    expect(r).toEqual({ ok: true, value: { zero_before: 0, zero_after: 1e-6, slip_events: 0 } });
  });
  // regression test for audit1#24 blank zero readings count as 0
  it("treats blank zero readings as 0 but rejects non-numeric and bad slip counts", () => {
    expect(parseCycle({ zeroBefore: "", zeroAfter: "", slips: "" })).toEqual({ ok: true, value: { zero_before: 0, zero_after: 0, slip_events: 0 } });
    expect(parseCycle({ zeroBefore: "x", zeroAfter: "0", slips: "0" }).ok).toBe(false);
    expect(parseCycle({ zeroBefore: "0", zeroAfter: "x", slips: "0" }).ok).toBe(false);
    expect(parseCycle({ zeroBefore: "0", zeroAfter: "0", slips: "1.5" }).ok).toBe(false);
    expect(parseCycle({ zeroBefore: "0", zeroAfter: "0", slips: "-1" }).ok).toBe(false);
  });
});

describe("cycleBody", () => {
  it("targets the setup phase", () => {
    const b = cycleBody({ zero_before: 0, zero_after: 0, slip_events: 0 });
    expect(b.phase).toBe("setup");
    expect(b.forced_early).toBe(false);
  });
});

describe("ClampCheckView", () => {
  it("explains the check and shows the form", () => {
    const html = renderToString(<ClampCheckView status={null} message="" busy={false} onCapture={() => undefined} />);
    expect(html).toContain("loose clamps");
    expect(html).toContain("Capture cycle");
  });
  it("shows progress and a failing verdict with advice", () => {
    const html = renderToString(<ClampCheckView status={status(false)} message="" busy={false} onCapture={() => undefined} />);
    expect(html).toContain("of");
    expect(html).toContain("Fail");
    expect(html).toContain("Re-tighten clamps");
  });
  it("shows no verdict until complete", () => {
    const html = renderToString(<ClampCheckView status={status(null)} message="" busy={false} onCapture={() => undefined} />);
    expect(html).not.toContain("Pass:");
    expect(html).not.toContain("Fail:");
  });
});

describe("ClampCheckPanel", () => {
  it("renders the loading state first", () => {
    expect(renderToString(<ClampCheckPanel />)).toContain("Loading procedure");
  });
  it("describes failures", () => {
    expect(apiErrorText({ kind: "http", status: 409, body: "x" })).toContain("409");
    expect(apiErrorText({ kind: "network", message: "down" })).toContain("down");
  });
});
