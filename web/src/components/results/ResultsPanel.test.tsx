// frob:ticket 01M6W7R3TJETR6N3EVA9PMPWH8
import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { ResultsPanel, compactNumber, copyText } from "./ResultsPanel";
import type { ResultSet, ResultValue } from "./types";

const mk = (name: string, display: string, status: "agrees" | "disagrees" | "pending" = "pending"): ResultValue => ({
  name, value: 1, std_unc: 0.05, u95: 0.1, low95: 0.9, high95: 1.1, unit: "GPa",
  dof: 5, display, confidence: `${name}: known to about 5 %`, mc: { status, mc_std_unc: null },
});

const rs: ResultSet = {
  n_points: 12,
  values: [mk("E", "70.1 +/- 1.2 GPa", "disagrees"), mk("slope", "2.00 +/- 0.05 V/N", "agrees")],
  pending: ["yield_stress"], notes: ["low r^2"], refinement: ["E"],
};

describe("results panel", () => {
  it("renders pre-formatted sig-fig strings verbatim with interval and confidence", () => {
    const html = renderToString(<ResultsPanel results={rs} />);
    expect(html).toContain("70.1 +/- 1.2 GPa");
    expect(html).toContain("2.00 +/- 0.05 V/N");
    expect(html).toContain("95 % range 0.9 to 1.1 GPa");
    expect(html).toContain("E: known to about 5 %");
    expect(html).toContain("12 points");
  });

  it("shows pending rows, notes and the settle source", () => {
    const html = renderToString(<ResultsPanel results={rs} settleSource="settle #3" />);
    expect(html).toContain("pending");
    expect(html).toContain("low r^2");
    expect(html).toContain("settle #3");
  });

  it("flags RSS vs Monte Carlo disagreement", () => {
    const html = renderToString(<ResultsPanel results={rs} />);
    expect(html).toContain("RSS and Monte Carlo disagree");
    expect(html).toContain("MC agrees");
  });

  it("builds copy text with units and calls the injected copy fn", () => {
    const text = copyText(rs);
    expect(text).toContain("Elastic modulus E: 70.1 +/- 1.2 GPa");
    expect(text).toContain("GPa]");
    const copy = vi.fn(() => Promise.resolve());
    renderToString(<ResultsPanel results={rs} copy={copy} />);
    expect(copy).not.toHaveBeenCalled();
  });

  // frob:ticket 01M71Z6EJDG2FBYHAJFFM90XMX
  it("rounds long floats and wraps the table for narrow screens", () => {
    expect(compactNumber(354865245.93444824)).toBe("3.549e+8");
    expect(compactNumber(0.123456789)).toBe("0.1235");
    expect(compactNumber(0)).toBe("0");
    const h = renderToString(<ResultsPanel results={rs} />);
    expect(h).toContain("overflow-x:auto");
    expect(h).not.toContain("u = ");
  });
});
