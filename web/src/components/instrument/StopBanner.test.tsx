// frob:ticket 01M7274EH583A30335TGGT6ZZ1
// frob:accept COV001 because="test file; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { fakeLive } from "../../state/testLive";
import { postReconnect, postResume } from "../../api/client";
import { InstrumentBarView } from "./InstrumentBar";
import { ResumeButton, StopBanner, canReconnect, resumeHint, stopMessage } from "./StopBanner";
import type { BackendFacts } from "./useBackendFacts";

type Dev = NonNullable<BackendFacts["device"]>;
const dev = (o: Partial<Dev>): Dev => ({ status: "simulated", attached: true, fault: null, hint: "", stopReason: null, acquisitionFault: null, ...o });

describe("StopBanner", () => {
  it("gives per-reason next steps even when simulated", () => {
    expect(stopMessage(dev({ stopReason: "idle" }))).toContain("Resume live readings");
    expect(stopMessage(dev({ stopReason: "finished" }))).toContain("Close the session, then Resume");
    expect(stopMessage(dev({ stopReason: "low_disk" }))).toContain("Free some disk space");
    expect(stopMessage(dev({}))).toBeNull();
    const l = fakeLive({ view: { source: "simulated" } });
    const html = renderToString(<InstrumentBarView view={l.view} conn={l.conn} calib={null} device={dev({ stopReason: "finished" })} />);
    expect(html).toContain("stop-banner");
  });
  it("shows acquisition faults and renders nothing when running", () => {
    expect(stopMessage(dev({ acquisitionFault: "usb timeout" }))).toContain("usb timeout");
    expect(renderToString(<StopBanner device={dev({})} />)).toBe("");
  });
  it("shows Reconnect only for disconnected or error", () => {
    expect(canReconnect("disconnected")).toBe(true);
    expect(canReconnect("error")).toBe(true);
    expect(canReconnect("connected")).toBe(false);
    const l = fakeLive();
    const html = renderToString(<InstrumentBarView view={l.view} conn={l.conn} calib={null} device={dev({ status: "disconnected" })} />);
    expect(html).toContain("ib-reconnect-btn");
  });
  it("shows No data when no frame has arrived", () => {
    const l = fakeLive();
    const html = renderToString(<InstrumentBarView view={l.view} conn={l.conn} calib={null} noFrames />);
    expect(html).toContain("No data");
    expect(html).not.toContain("[ok] OK");
  });
});

describe("postReconnect", () => {
  it("POSTs /api/device/reconnect", async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "connected", attached: true, hint: "" }), { status: 200 }));
    const r = await postReconnect(f);
    expect(r.ok).toBe(true);
    expect(f).toHaveBeenCalledWith("/api/device/reconnect", expect.objectContaining({ method: "POST" }));
  });
  it("returns an error on network failure", async () => {
    const f = vi.fn().mockRejectedValue(new Error("down"));
    const r = await postReconnect(f);
    expect(r.ok).toBe(false);
  });
});

// frob:ticket 01M727MMWZ8X2B29300XHTWZ46
describe("Resume live readings", () => {
  it("shows the button only for the idle stop reason", () => {
    expect(renderToString(<StopBanner device={dev({ stopReason: "idle" })} />)).toContain("ib-resume-btn");
    expect(renderToString(<StopBanner device={dev({ stopReason: "finished" })} />)).not.toContain("ib-resume-btn");
    expect(renderToString(<ResumeButton post={vi.fn()} />)).not.toContain("disabled");
  });
  it("extracts the 409 hint from a problem body", () => {
    expect(resumeHint(JSON.stringify({ hint: "Free disk space." }))).toBe("Free disk space.");
    expect(resumeHint("not json")).toContain("data is safe");
  });
  it("postResume POSTs the resume path and maps 409 to an http error", async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ hint: "h" }), { status: 409 }));
    const r = await postResume(f);
    expect(f).toHaveBeenCalledWith("/api/acquisition/resume", expect.objectContaining({ method: "POST" }));
    expect(r).toMatchObject({ ok: false, error: { kind: "http", status: 409 } });
    const g = vi.fn().mockResolvedValue(new Response(JSON.stringify({ streaming: true }), { status: 200 }));
    expect(await postResume(g as unknown as typeof fetch)).toMatchObject({ ok: true, value: { streaming: true } });
  });
});
