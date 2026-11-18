// frob:ticket 01M6WZX63YFEAYQTPJXE2BTRN2
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SessionSetup, isRecoverable, slugFrom, specimenFrom } from "./SessionSetup";
import { provenanceBadge } from "../../state/provenance";
import { closedExportUrl, csvFormatFor, downloadClosedExport, downloadFailureText, failureText } from "./sessionApi";

describe("SessionSetup", () => {
  it("offers recovered-data download only for open or incomplete sessions", () => {
    expect(isRecoverable("open")).toBe(true);
    expect(isRecoverable("incomplete")).toBe(true);
    expect(isRecoverable("closed")).toBe(false);
  });

  it("renders the resume list and the new-session form", () => {
    const html = renderToString(<SessionSetup onOpened={() => undefined} />);
    expect(html).toContain("Session setup");
    expect(html).toContain("Create session");
    expect(html).toContain("original is kept");
  });

  it("slugs names and drops blank specimen fields", () => {
    expect(slugFrom("Wire #3 / A")).toBe("wire-3-a");
    expect(slugFrom("   ")).toBe("session");
    expect(specimenFrom({ name: " a ", material: "" })).toEqual({ name: "a" });
  });

  it("describes failures", () => {
    expect(failureText({ kind: "transport", error: { kind: "http", status: 500, body: "" } })).toContain("500");
  });

  it("builds the read-only export url and knows the lctt csv format", () => {
    expect(closedExportUrl("a b", "lctt-csv")).toBe("/api/sessions/a%20b/export/lctt-csv");
    expect(csvFormatFor("lctt")).toBe("lctt-csv");
    expect(csvFormatFor("other")).toBeNull();
  });

  it("downloads a closed session with a plain GET and no body", async () => {
    const calls: unknown[][] = [];
    const f = ((...a: unknown[]) => {
      calls.push(a);
      return Promise.resolve(new Response("a,b\n", { status: 200, headers: { "Content-Disposition": 'attachment; filename="s-lctt-csv.csv"' } }));
    }) as unknown as typeof fetch;
    const r = await downloadClosedExport("s", "lctt-csv", f);
    expect(r.ok).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual(["/api/sessions/s/export/lctt-csv"]);
  });

  it("shows the problem detail and hint when the server refuses", async () => {
    const body = JSON.stringify({ title: "session open", detail: "s is the open session", hint: "Close it first." });
    const f = (() => Promise.resolve(new Response(body, { status: 409 }))) as unknown as typeof fetch;
    const r = await downloadClosedExport("s", "lctt-csv", f);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      const text = downloadFailureText(r.error);
      expect(text).toContain("s is the open session");
      expect(text).toContain("Close it first.");
    }
  });
});

describe("SessionSetup SYNTHETIC badge", () => {
  it("source marks synthetic sessions with a visible badge", async () => {
    const src = (await import("node:fs")).readFileSync(new URL("./SessionSetup.tsx", import.meta.url), "utf8");
    expect(src).toContain("s.provenance.synthetic ?");
    expect(src).toContain("SYNTHETIC</strong>");
  });
});

// frob:ticket 01M72TJ0CQPCRKAW2EWSFP9Y8Z
describe("session provenance badge", () => {
  const stamp = (source: "real" | "synthetic" | "unknown", synthetic: boolean) => ({ source, synthetic, label: "", warning: "" });
  it("labels unknown as unknown, never synthetic or real", () => {
    expect(provenanceBadge(stamp("unknown", false))).toBe("Provenance unknown");
    expect(provenanceBadge(stamp("synthetic", true))).toBe("SYNTHETIC");
    expect(provenanceBadge(stamp("real", false))).toBeNull();
  });
});
