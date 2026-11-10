// frob:ticket 01M727TR8PNCVA3CA5ZAVFBREF
// frob:accept COV001 because="test file; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DebugStripView, deviceText } from "../instrument/DebugStrip";
import type { BackendFacts } from "../instrument/useBackendFacts";

const EMPTY: BackendFacts = { save: null, device: null, session: null, rootLockOk: null, dataRoot: null, version: null, lastError: null };
type Dev = NonNullable<BackendFacts["device"]>;
const dev = (o: Partial<Dev>): Dev => ({ status: "connected", attached: true, fault: null, hint: "", stopReason: null, acquisitionFault: null, ...o });
const rts = (el: React.JSX.Element): string => renderToString(el).replaceAll("<!-- -->", "");

describe("DebugStrip device and seq rows", () => {
  // covers web/src/components/instrument/DebugStrip.tsx::deviceText
  it("renders a faulted device as a fault with its reason, not [ok]", () => {
    const t = deviceText(dev({ status: "error", attached: true, fault: "fifo overrun" }));
    expect(t).toContain("(!) fault");
    expect(t).toContain("fifo overrun");
    expect(t).not.toContain("[ok]");
  });

  // covers web/src/components/instrument/DebugStrip.tsx::deviceText
  it("renders acquisition faults and a healthy device correctly", () => {
    expect(deviceText(dev({ acquisitionFault: "usb dropout" }))).toContain("usb dropout");
    expect(deviceText(dev({}))).toBe("[ok] connected");
    expect(deviceText(dev({ status: "disconnected", attached: false }))).toBe("(!) disconnected");
  });

  // covers web/src/components/instrument/DebugStrip.tsx::DebugStripView
  it("labels the WS frame seq and WAL seq separately", () => {
    const html = rts(<DebugStripView meta={{ seq: 900, durableSeq: 40, enqueuedSeq: 42, dtS: 0.01, atMs: 100 }} nowMs={150} facts={EMPTY} backend="[ok] up" />);
    expect(html).toContain("WS frame seq");
    expect(html).toContain("WAL seq (durable / queued)");
    expect(html).toContain("40 / 42");
    expect(html).not.toContain("Seq / durable");
  });
});
