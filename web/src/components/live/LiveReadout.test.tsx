// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString as rts } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { fakeLive, withLive } from "../../state/testLive";
import { LiveReadout, LiveReadoutView } from "./LiveReadout";
import { settleText } from "./settle";
import { LiveTrace } from "./TraceCanvas";
import type { LiveView } from "../../screens/run/live";

const html = (el: React.JSX.Element): string => rts(el).replaceAll("<!-- -->", "");
const view = (o: Partial<LiveView> = {}): LiveView =>
  ({ volts: 1.2345, driftVps: 0.0012, signal: "ok", motion: "settled", source: "connected", stale: false, ...o });

describe("LiveReadoutView", () => {
  it("connected and settled: big volts, drift, glyph plus word", () => {
    const out = html(<LiveReadoutView view={view()} conn={{ status: "open" }} />);
    expect(out).toContain("1.2345");
    expect(out).toContain("1.2 mV/s");
    expect(out).toContain("[ok] Settled");
    expect(out).toContain("[ok] OK");
    expect(out).toContain("[ok] Connected");
    expect(out).not.toContain("sim-banner");
  });

  it("simulated source shows the prominent SIMULATED banner", () => {
    const out = html(<LiveReadoutView view={view({ source: "simulated" })} conn={{ status: "open" }} />);
    expect(out).toContain('data-testid="sim-banner"');
    expect(out).toContain("SIMULATED DATA");
  });

  it("stale data is flagged in words and the connection shows reconnecting", () => {
    const out = html(<LiveReadoutView view={view({ stale: true, source: "disconnected", motion: "creeping" })} conn={{ status: "reconnecting", attempt: 2, delayMs: 500 }} />);
    expect(out).toContain("(!) Stale - not current");
    expect(out).toContain("(!) Creeping");
    expect(out).toContain("Reconnecting (attempt 2)");
    expect(out).toContain('data-stale="true"');
  });

  it("no data yet shows dashes", () => {
    const out = html(<LiveReadoutView view={view({ volts: null, driftVps: null, motion: "unknown" })} conn={{ status: "open" }} />);
    expect(out).toContain("--");
    expect(out).toContain("Measuring...");
  });

  it("saturated signal is worded, not colour only", () => {
    expect(html(<LiveReadoutView view={view({ signal: "saturated" })} conn={{ status: "open" }} />)).toContain("(!) SATURATED");
  });
});

describe("context-fed cards", () => {
  it("LiveReadout reads the shared feed", () => {
    expect(html(withLive(<LiveReadout />, fakeLive({ view: { volts: 2.5 } })))).toContain("2.5000");
  });
  it("LiveTrace renders the shared canvas", () => {
    expect(html(withLive(<LiveTrace />))).toContain("live-canvas");
  });
  it("settleText words", () => {
    expect(settleText(view())).toBe("[Settled]");
    expect(settleText(view({ motion: "creeping", driftVps: null }))).toBe("[Creeping]");
  });
});
