// frob:ticket 01M72ZDQGAN0VQRKHM489H28J1
// creates:web/src/components/wizard/ExportNow.test.tsx
import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { EXPORT_NOW_FORMATS, ExportNow, exportNow } from "./ExportNow";

describe("exportNow", () => {
  it("saves the server file under the server-chosen name", async () => {
    const save = vi.fn();
    const f = vi.fn().mockResolvedValue(new Response("a,b", { status: 200, headers: { "Content-Disposition": 'attachment; filename="s-lctt-csv-partial.csv"', "X-SADI-Saved": "exports/x/1.csv", "X-SADI-Provenance": "real" } }));
    const msg = await exportNow("lctt-csv-partial", save, f);
    expect(save).toHaveBeenCalledWith(expect.any(Blob), "s-lctt-csv-partial.csv");
    expect(msg).toContain("exports/x/1.csv");
  });

  it("returns the refusal text and saves nothing when the server refuses", async () => {
    const save = vi.fn();
    const body = JSON.stringify({ title: "too few points", detail: "Calibrate first.", hint: "Capture cal points.", status: 422 });
    const f = vi.fn().mockResolvedValue(new Response(body, { status: 422 }));
    const msg = await exportNow("lctt-csv-partial", save, f);
    expect(save).not.toHaveBeenCalled();
    expect(msg).toContain("too few points");
  });
});

describe("ExportNow", () => {
  it("renders one enabled button per mid-run format", () => {
    const html = renderToString(<ExportNow />);
    for (const f of EXPORT_NOW_FORMATS) expect(html).toContain(f.label);
    expect(html).not.toContain("disabled");
  });
});
