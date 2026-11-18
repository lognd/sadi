// frob:ticket 01M72YKF3EN8RJX7RCH78JDPQC
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { RepeatedReadingsPanel } from "./RepeatedReadingsPanel";

describe("RepeatedReadingsPanel", () => {
  it("renders the readings and instrument-uncertainty inputs", () => {
    const html = renderToString(<RepeatedReadingsPanel label="diameter" unit="m" onUse={vi.fn()} />).replaceAll("<!-- -->", "");
    expect(html).toContain("Repeated readings of diameter");
    expect(html).toContain('name="readings"');
    expect(html).toContain('name="u_inst"');
  });
});
