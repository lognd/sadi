// frob:ticket 01M727YGXCC6ZFVHWHG64KFA7D
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { exportErrorText, fetchRunExport } from "./exportTrace";

const reply = (headers: Record<string, string>, status = 200): typeof fetch =>
  (() => Promise.resolve(new Response("a,b\n1,2\n", { status, headers }))) as typeof fetch;

describe("fetchRunExport filename", () => {
  it("uses the Content-Disposition name from the server", async () => {
    const r = await fetchRunExport("lctt-csv", reply({ "Content-Disposition": 'attachment; filename="run-7.csv"' }));
    expect(r.ok && r.value.filename).toBe("run-7.csv");
  });

  it("keeps a server SYNTHETIC- prefix without doubling it", async () => {
    const r = await fetchRunExport("lctt-csv", reply({ "Content-Disposition": "attachment; filename=SYNTHETIC-run-7.csv" }));
    expect(r.ok && r.value.filename).toBe("SYNTHETIC-run-7.csv");
  });

  it("prefixes SYNTHETIC- when the provenance header says synthetic", async () => {
    const r = await fetchRunExport("lctt-csv", reply({ "Content-Disposition": 'attachment; filename="run-7.csv"', "X-Sadi-Provenance": "synthetic" }));
    expect(r.ok && r.value.filename).toBe("SYNTHETIC-run-7.csv");
  });

  it("falls back to a default name when no header is sent", async () => {
    const r = await fetchRunExport("lctt-csv", reply({}));
    expect(r.ok && r.value.filename).toBe("sadi-lctt-csv.csv");
  });
});

describe("fetchRunExport failures", () => {
  it("returns an http error with user-facing text", async () => {
    const r = await fetchRunExport("lctt-csv", reply({}, 409));
    expect(r.ok).toBe(false);
    if (!r.ok) expect(exportErrorText(r.error)).toContain("HTTP 409");
  });

  it("returns a network error instead of throwing", async () => {
    const r = await fetchRunExport("lctt-csv", (() => Promise.reject(new Error("down"))) as typeof fetch);
    expect(!r.ok && exportErrorText(r.error)).toContain("down");
  });
});
