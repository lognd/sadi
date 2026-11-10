// frob:ticket 01M72VM5RSJM7EMREPXDYDN79W
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { isRequestIdReused, problemText } from "../review/api";
import { buildSpecimenBody, postCapture, wroteNothing, type CaptureBody } from "./capture";
import type { LiveView } from "./live";

const view: LiveView = { volts: 1, driftVps: 0, signal: "ok", motion: "settled", source: "simulated", stale: false };
const problem = (type: string, hint: string, detail = "d"): typeof fetch => () =>
  Promise.resolve(new Response(JSON.stringify({ type, title: "T", status: 409, detail, hint }), { status: 409 }));
const body = (): CaptureBody => ({ phase: "load", inputs: {}, window: { first_raw_seq: 1, last_raw_seq: 1 }, settled: true, forced_early: false, drift_rate: null, request_id: "x" });

describe("capture failure text", () => {
  it("parses the problem once and shows the hint, never raw JSON or an HTTP code", async () => {
    const r = await postCapture(body(), problem("urn:sadi:error:conflict:no_device", "Connect the device."));
    expect(!r.ok && problemText(r.error, "Capture")).toBe("Capture refused. Connect the device.");
    expect(!r.ok && problemText(r.error, "Capture")).not.toMatch(/HTTP|\{/);
  });
  it("falls back to detail, then to a generic line for a non-JSON body", async () => {
    const d = await postCapture(body(), problem("urn:x", "", "Mass is too big."));
    expect(!d.ok && problemText(d.error, "Capture")).toBe("Capture refused. Mass is too big.");
    const raw = await postCapture(body(), () => Promise.resolve(new Response("nope", { status: 500 })));
    expect(!raw.ok && problemText(raw.error, "Load change")).toBe("Load change was refused. Try again.");
  });
  it("only request_id_reused clears the frozen id", async () => {
    const reused = await postCapture(body(), problem("urn:sadi:error:conflict:request_id_reused", "x"));
    const other = await postCapture(body(), problem("urn:sadi:error:conflict:no_device", "x"));
    expect(!reused.ok && isRequestIdReused(reused.error)).toBe(true);
    expect(!other.ok && isRequestIdReused(other.error)).toBe(false);
  });
  it("the specimen body carries its own request id", () => {
    expect(buildSpecimenBody({ diameter: 0.001 }, 3, view, "sp-1")).toMatchObject({ phase: "specimen", request_id: "sp-1" });
  });
});

// frob:ticket 01M72YAFW769RWFJXZ8TBBJ4QS
describe("wroteNothing", () => {
  const http = (status: number, type: string) => ({ kind: "http" as const, status, body: "", problem: { type, title: "T", detail: "", hint: "" } });
  it("is true for 4xx refusals such as 409 no_device and 422 bad_window", () => {
    expect(wroteNothing(http(409, "urn:sadi:error:conflict:no_device"))).toBe(true);
    expect(wroteNothing(http(422, "urn:sadi:error:wizard:bad_window"))).toBe(true);
  });
  it("is true for 503 Backpressure only", () => {
    expect(wroteNothing(http(503, "urn:sadi:error:writer:backpressure"))).toBe(true);
    expect(wroteNothing(http(503, "urn:sadi:error:writer:stalled"))).toBe(false);
  });
  it("is false for network errors and 5xx, whose outcome is unknown", () => {
    expect(wroteNothing({ kind: "network", message: "x" })).toBe(false);
    expect(wroteNothing(http(500, "urn:x"))).toBe(false);
  });
});
