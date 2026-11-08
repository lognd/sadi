// frob:ticket 01M6W7RATGKGPEYSMC5H8WGMBV
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { FormatList, ProblemAlert, ReportView, exportFigureFormat, figureFileName } from "./ExportScreen";
import { exportUrl, getExportFormats, toProblem } from "./api";
import type { ResultSet } from "./types";

const rs: ResultSet = {
  n_points: 6,
  values: [{ name: "E", value: 70, std_unc: 1, u95: 2, low95: 68, high95: 72, unit: "GPa", dof: 4,
    display: "70.0 +/- 2.0 GPa", confidence: "Confident to 3 %", mc: { status: "agrees", mc_std_unc: 1 } }],
  pending: ["sigma_y"], notes: ["settle value 1.2 mm fed E"], refinement: [],
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
  });

  it("exports an svg figure and reports errors as problems", async () => {
    const scene = { title: "t", width: 200, height: 100, xAxis: { label: "x" }, yAxis: { label: "y" },
      series: [{ id: "s", label: "s", x: [0, 1], y: [0, 1], style: "line" }] };
    const save = vi.fn();
    const ok = await exportFigureFormat("fig", { format: "svg" }, () => json(scene), save);
    expect(ok).toBeNull();
    expect(save).toHaveBeenCalledWith(expect.any(Blob), "fig.svg");
    const bad = await exportFigureFormat("nope", { format: "svg" },
      () => json({ title: "Unknown", detail: "x", hint: "use fig" }, 404), save);
    expect(bad?.hint).toBe("use fig");
    expect(save).toHaveBeenCalledTimes(1);
  });
});
