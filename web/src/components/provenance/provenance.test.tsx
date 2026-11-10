// frob:ticket ~60KQX63
// frob:accept COV001 because="test file; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { FormatList, ReportView } from "../../screens/export/ExportScreen";
import { currentlySynthetic, EXPORT_PREFIX, exportFilename, isSynthetic, SYNTHETIC_LABEL, useProvenance, type DataProvenance } from "../../state/provenance";
import { fakeLive } from "../../state/testLive";
import { InstrumentBarView } from "../instrument/InstrumentBar";
import { SyntheticBanner } from "./SyntheticBanner";

const SYN: DataProvenance = { source: "synthetic", synthetic: true, label: SYNTHETIC_LABEL, warning: "Simulated specimen." };
const REAL: DataProvenance = { source: "real", synthetic: false, label: "", warning: "" };
const FORMATS = [{ id: "csv32", title: "CSV", media_type: "text/csv", download: true }];

afterEach(() => { useProvenance.setState({ provenance: null }); });

function bar(p: DataProvenance): string {
  const l = fakeLive();
  return renderToString(<InstrumentBarView view={l.view} conn={l.conn} calib={null} provenance={p} />);
}

describe("SyntheticBanner", () => {
  it("shows label, status role and icon for synthetic data", () => {
    const html = renderToString(<SyntheticBanner provenance={SYN} />);
    expect(html).toContain(SYNTHETIC_LABEL);
    expect(html).toContain('role="status"');
    expect(html).toContain("<svg");
  });
  it("renders nothing for real or missing provenance", () => {
    expect(renderToString(<SyntheticBanner provenance={REAL} />)).toBe("");
    expect(renderToString(<SyntheticBanner />)).toBe("");
  });
  it("isSynthetic is false unless explicitly stamped", () => {
    expect(isSynthetic(null)).toBe(false);
    expect(isSynthetic(REAL)).toBe(false);
    expect(isSynthetic(SYN)).toBe(true);
  });
});

describe("instrument bar", () => {
  it("shows the banner when the store is synthetic", () => {
    expect(bar(SYN)).toContain(SYNTHETIC_LABEL);
  });
  it("never shows it for real data", () => {
    expect(bar(REAL)).not.toContain("SYNTHETIC");
  });
});

describe("export views", () => {
  const results = { n_points: 0, values: [], pending: [], notes: [], refinement: [], provenance: [] };
  it("report and download list carry the banner and prefix when synthetic", () => {
    expect(renderToString(<ReportView results={{ ...results, data_provenance: SYN }} />)).toContain(SYNTHETIC_LABEL);
    const html = renderToString(<FormatList formats={FORMATS} dpi={300} provenance={SYN} />);
    expect(html).toContain(SYNTHETIC_LABEL);
    expect(html).toContain(EXPORT_PREFIX);
  });
  it("real data shows no banner and no prefix", () => {
    expect(renderToString(<ReportView results={{ ...results, data_provenance: REAL }} />)).not.toContain("SYNTHETIC");
    expect(renderToString(<FormatList formats={FORMATS} dpi={300} provenance={REAL} />)).not.toContain("SYNTHETIC");
  });
  it("store feeds currentlySynthetic", () => {
    useProvenance.getState().observe(SYN);
    expect(currentlySynthetic()).toBe(true);
    useProvenance.getState().observe(REAL);
    expect(currentlySynthetic()).toBe(false);
  });
  it("exportFilename prefixes once and only when synthetic", () => {
    expect(exportFilename("a.csv", true)).toBe("SYNTHETIC-a.csv");
    expect(exportFilename("SYNTHETIC-a.csv", true)).toBe("SYNTHETIC-a.csv");
    expect(exportFilename("a.csv", false)).toBe("a.csv");
  });
});
