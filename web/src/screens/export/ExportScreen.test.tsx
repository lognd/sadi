// frob:ticket 01M6WVTVH19EXW341V5K8SM7Z4
// frob:ticket 01M6W7RATGKGPEYSMC5H8WGMBV
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { FormatList, ProblemAlert, ReportView, quantityLabel, sampleSpan, exportFigureFormat, figureFileName } from "./ExportScreen";
import { downloadExport, exportUrl, getExportFormats, savedMessage, toProblem } from "./api";
import { exportFilename } from "../../state/provenance";
import { figureDataScenes } from "./figureScenes";
import type { ResultSet } from "./types";

const rs: ResultSet = {
  n_points: 6,
  values: [{ name: "E", value: 70, std_unc: 1, u95: 2, low95: 68, high95: 72, unit: "GPa", dof: 4,
    display: "70.0 +/- 2.0 GPa", confidence: "Confident to 3 %", mc: { status: "agrees", mc_std_unc: 1 } }],
  pending: ["sigma_y"], notes: ["settle value 1.2 mm fed E"], refinement: [],
  provenance: [{ name: "E", point_ids: ["p1", "p2"], first_sample: 10, last_sample: 45, algorithm: "lctt.recompute" },
    { name: "G", point_ids: [], first_sample: null, last_sample: null, algorithm: "lctt.recompute" }],
};
const json = (b: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(b), { status }));

describe("export screen", () => {
  it("renders the report with value, interval and notes", () => {
    const h = renderToString(<ReportView results={rs} />);
    expect(h).toContain("70.0 +/- 2.0 GPa");
    expect(h).toContain("68 to 72 GPa");
    expect(h).toContain("settle value 1.2 mm fed E");
    expect(h).toContain("Pending: sigma_y");
    expect(renderToString(<ReportView results={null} />)).toContain("No results yet");
  });

  it("renders provenance: point ids, sample span, algorithm", () => {
    const h = renderToString(<ReportView results={rs} />);
    expect(h).toContain("2 points");
    expect(h).toContain("10 to 45");
    expect(h).toContain("lctt.recompute");
    const none = renderToString(<ReportView results={{ ...rs, provenance: [] }} />);
    expect(none).not.toContain('data-testid="provenance"');
  });

  it("shows a clear message for an empty format list", () => {
    expect(renderToString(<FormatList formats={[]} dpi={300} />)).toContain("declares no export formats");
  });

  it("lists CSV as a link and figures as buttons", () => {
    const h = renderToString(<FormatList dpi={300} formats={[
      { id: "csv32", title: "CSV", media_type: "text/csv", download: true },
      { id: "fig", title: "Stress-strain", media_type: "application/json", download: false }]} />);
    expect(h).toContain('href="/api/export/csv32"');
    expect(h).toContain("Export Stress-strain as PNG");
    expect(h).toContain("Export Stress-strain as SVG");
  });

  // frob:ticket 01M6XAASK3B2CWRRHQZ995FN7K
  it("puts the CSV link before the dpi select and figure buttons even when listed after", () => {
    const h = renderToString(<FormatList dpi={300} formats={[
      { id: "fig", title: "Stress-strain", media_type: "application/json", download: false },
      { id: "csv32", title: "CSV", media_type: "text/csv", download: true }]} />);
    const link = h.indexOf("Download CSV");
    expect(link).toBeGreaterThan(-1);
    expect(link).toBeLessThan(h.indexOf("<select"));
    expect(link).toBeLessThan(h.indexOf("Export Stress-strain as PNG"));
  });

  it("parses problem+json and shows the hint", () => {
    const p = toProblem({ kind: "http", status: 409, body: JSON.stringify({ title: "No session", detail: "none open", hint: "Open a session" }) });
    expect(p).toMatchObject({ title: "No session", hint: "Open a session", status: 409 });
    const h = renderToString(<ProblemAlert p={p} />);
    expect(h).toContain("Hint: Open a session");
    expect(toProblem({ kind: "http", status: 500, body: "boom" }).detail).toBe("boom");
    expect(toProblem({ kind: "network", message: "down" }).title).toBe("Network error");
  });

  it("builds urls and fetches formats", async () => {
    expect(exportUrl("a b")).toBe("/api/export/a%20b");
    const r = await getExportFormats(() => json([]));
    expect(r).toEqual({ ok: true, value: [] });
    expect(figureFileName("fig", "svg")).toBe("fig.svg");
    expect(figureFileName("fig", "svg", "lab-a")).toBe("lab-a-fig.svg");
  });

  it("exports figure data as one svg per figure and reports errors as problems", async () => {
    const data = {
      calibration: { volts: [1, 2, 3], height_m: [0.01, 0.02, 0.031], fit: { slope_m_per_v: 0.01, intercept_m: 0, r2: 0.999, n: 3,
        band_volts: [1, 2, 3], band_height_m: [0.01, 0.02, 0.03], band_half_width_m: [0.001, 0.001, 0.001] } },
      stress_strain: { point_ids: ["a", "b"], strain: [0.001, 0.002], stress_mpa: [70, 140], excluded: [false, true] },
    };
    const save = vi.fn();
    const ok = await exportFigureFormat("fig", { format: "svg" }, () => json(data), save);
    expect(ok).toBeNull();
    expect(save).toHaveBeenCalledWith(expect.any(Blob), "fig-calibration.svg");
    expect(save).toHaveBeenCalledWith(expect.any(Blob), "fig-stress-strain.svg");
    const bad = await exportFigureFormat("nope", { format: "svg" },
      () => json({ title: "Unknown", detail: "x", hint: "use fig" }, 404), save);
    expect(bad?.hint).toBe("use fig");
    const odd = await exportFigureFormat("fig", { format: "svg" }, () => json({ series: [] }), save);
    expect(odd?.title).toBe("Figure data cannot be drawn");
    expect(save).toHaveBeenCalledTimes(2);
  });

  it("says so when the session has no points to plot", async () => {
    const empty = {
      calibration: { volts: [], height_m: [], fit: null },
      stress_strain: { point_ids: [], strain: [], stress_mpa: [], excluded: [] },
    };
    const save = vi.fn();
    const p = await exportFigureFormat("fig", { format: "svg" }, () => json(empty), save);
    expect(p?.title).toBe("Nothing to plot yet");
    expect(save).not.toHaveBeenCalled();
  });

  // frob:ticket 01M71Z6EJDG2FBYHAJFFM90XMX
  it("states the data source and hides empty 0-to-0 spans (Audit1 #36)", () => {
    const real = renderToString(<ReportView results={{ ...rs, data_provenance: { source: "real", synthetic: false, label: "", warning: "" } }} />);
    expect(real).toContain("real measurement");
    const syn = renderToString(<ReportView results={{ ...rs, data_provenance: { source: "synthetic", synthetic: true, label: "SYNTHETIC", warning: "w" } }} />);
    expect(syn).toContain("SYNTHETIC (simulated");
    expect(sampleSpan({ name: "x", point_ids: [], first_sample: 0, last_sample: 0, algorithm: "a" })).toBe("-");
    expect(quantityLabel("secant_modulus")).toBe("Secant modulus at last point");
    expect(renderToString(<ReportView results={rs} />)).toContain("overflow-x:auto");
  });
});

// frob:ticket 01M7230XGWSR1B8D93KW5M4P7D
describe("download via fetch", () => {
  it("non-2xx returns an error that becomes a problem with detail and hint", async () => {
    const body = JSON.stringify({ title: "Not ready", detail: "NotReady: calibration needed", hint: "Finish calibration." });
    const r = await downloadExport("lctt-csv", (() => Promise.resolve(new Response(body, { status: 422 }))));
    expect(r.ok).toBe(false);
    if (r.ok) return;
    const p = toProblem(r.error);
    expect(p.detail).toContain("calibration needed");
    expect(p.hint).toBe("Finish calibration.");
    expect(renderToString(<ProblemAlert p={p} />)).toContain("Hint: Finish calibration.");
  });

  it("success carries the saved-copy header and a message", async () => {
    const res = new Response("a,b\n", { status: 200, headers: { "X-SADI-Saved": "exports/lctt-csv/x.csv", "Content-Disposition": 'attachment; filename="x.csv"' } });
    const r = await downloadExport("lctt-csv", (() => Promise.resolve(res)));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.value.saved).toBe("exports/lctt-csv/x.csv");
    expect(r.value.filename).toContain("x.csv");
    expect(savedMessage(r.value.saved)).toBe("Saved a copy in exports/lctt-csv/x.csv");
    expect(savedMessage("failed")).toContain("could not keep");
    expect(savedMessage("")).toBe("");
  });

  // frob:ticket 01M72D3CTDED2MGDY721RSM8M4
  it("splits the stress-strain scene by phase", () => {
    const d = { calibration: { volts: [], height_m: [], fit: null }, stress_strain: { point_ids: ["a", "b", "c"], strain: [0.001, 0.002, 0.003], stress_mpa: [70, 140, 90],
      excluded: [false, false, false], phase: ["elastic", "elastic", "plastic"] } };
    const scenes = figureDataScenes(d);
    const ss = scenes.find((n) => n.suffix.includes("stress"));
    expect(ss).toBeDefined();
    expect(JSON.stringify(ss?.scene)).toContain("plastic");
  });

  // frob:ticket 01M72D3CTDED2MGDY721RSM8M4
  it("keeps the server-provided filename when provenance is stamped", async () => {
    const mk = (prov: string, name: string) => new Response("a\n", { status: 200, headers: { "X-SADI-Provenance": prov, "Content-Disposition": `attachment; filename="${name}"` } });
    const real = await downloadExport("lctt-csv", (() => Promise.resolve(mk("real", "RECOVERED-x.csv"))));
    expect(real.ok && real.value.filename).toBe("RECOVERED-x.csv");
    const syn = await downloadExport("lctt-csv", (() => Promise.resolve(mk("synthetic", "RECOVERED-SYNTHETIC-x.csv"))));
    expect(syn.ok && syn.value.filename).toBe("RECOVERED-SYNTHETIC-x.csv");
    expect(exportFilename("RECOVERED-SYNTHETIC-x.csv", true)).toBe("RECOVERED-SYNTHETIC-x.csv");
  });

  it("network failure becomes a network error", async () => {
    const r = await downloadExport("lctt-csv", (() => Promise.reject(new Error("down"))));
    expect(r.ok).toBe(false);
  });
});
