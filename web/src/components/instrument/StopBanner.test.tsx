// frob:ticket 01M7274EH583A30335TGGT6ZZ1
// frob:accept COV001 because="test file; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { fakeLive } from "../../state/testLive";
import { postReconnect } from "../../api/client";
import { InstrumentBarView } from "./InstrumentBar";
import { StopBanner, canReconnect, stopMessage } from "./StopBanner";
import type { BackendFacts } from "./useBackendFacts";

type Dev = NonNullable<BackendFacts["device"]>;
const dev = (o: Partial<Dev>): Dev => ({ status: "simulated", attached: true, fault: null, hint: "", stopReason: null, acquisitionFault: null, ...o });

describe("StopBanner", () => {
  it("gives per-reason next steps even when simulated", () => {
    expect(stopMessage(dev({ stopReason: "idle" }))).toContain("Mark load change");
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
