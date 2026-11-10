// frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5
// frob:accept COV001 because="test file; TypeScript test discovery needs grimble, not installed here"
import { readFileSync } from "node:fs";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { HEALTH_POLL_MS } from "../../App";
import { isBackendDown } from "../../screens/WizardHost";
import { fakeLive } from "../../state/testLive";
import { FrontPanel } from "../wizard/FrontPanel";
import { StatusBar } from "../status/StatusBar";
import { DebugStripView } from "./DebugStrip";
import { InstrumentBarView, settleWord } from "./InstrumentBar";
import { fetchFacts, type BackendFacts } from "./useBackendFacts";

const EMPTY: BackendFacts = { save: null, device: null, session: null, rootLockOk: null, dataRoot: null, version: null, lastError: null };
const rts = (el: React.JSX.Element): string => renderToString(el).replaceAll("<!-- -->", "");

describe("audit1 shell fixes", () => {
  // covers web/src/components/instrument/DebugStrip.tsx::DebugStripView
  it("#10 shows the data folder without a misleading default suffix", () => {
    const html = rts(<DebugStripView meta={null} nowMs={0} facts={{ ...EMPTY, dataRoot: "/srv/sadi" }} backend="[ok] up" />);
    expect(html).toContain("/srv/sadi");
    expect(html).not.toContain("default; may differ");
  });

  // covers web/src/App.tsx::App
  it("#16 polls health on a short period", () => {
    expect(HEALTH_POLL_MS).toBeLessThanOrEqual(5000);
  });

  // covers web/src/screens/WizardHost.tsx::isBackendDown
  it("#16 treats network and gateway failures as backend-down, not as a setup screen", () => {
    expect(isBackendDown({ kind: "transport", error: { kind: "network", message: "x" } })).toBe(true);
    expect(isBackendDown({ kind: "transport", error: { kind: "http", status: 502, body: "" } })).toBe(true);
    expect(isBackendDown({ kind: "transport", error: { kind: "http", status: 500, body: "" } })).toBe(false);
  });

  // covers web/src/components/instrument/InstrumentBar.tsx::InstrumentBarView
  it("#28 disconnected bar shows the plug-in hint and no ok marks for settle/signal", () => {
    const l = fakeLive({ view: { source: "disconnected" } });
    const html = rts(<InstrumentBarView view={l.view} conn={l.conn} calib={null} deviceHint="Plug in the instrument" />);
    expect(html).toContain("Plug in the instrument");
    expect(html).toContain("no signal");
    expect(html).not.toContain("[ok] OK");
    expect(settleWord(l.view)).not.toContain("[ok]");
  });

  // covers web/src/components/status/StatusBar.tsx::StatusBar
  it("#28 status bar says no signal instead of (ok) when disconnected", () => {
    const html = rts(<StatusBar source="disconnected" motion="settled" signal="ok" save={{ state: "no-session", text: "No session" }} />);
    expect(html).toContain("No signal");
    expect(html).not.toContain("(ok)");
  });

  // covers web/src/components/instrument/useBackendFacts.ts::fetchFacts
  it("#37 skips /api/session when asked and keeps the previous session", async () => {
    const f = vi.fn(() => Promise.resolve(new Response("{}")));
    const prev = { ...EMPTY, session: { name: "s", lab: "l", durableSeq: 1 } };
    const out = await fetchFacts(prev, f, false);
    const paths = (f.mock.calls as string[][]).map((c) => c[0]);
    expect(paths).not.toContain("/api/session");
    expect(out.session).toEqual(prev.session);
    await fetchFacts(prev, f, true);
    expect((f.mock.calls as string[][]).map((c) => c[0])).toContain("/api/session");
  });

  // covers web/src/styles.css
  it("#38 step glyphs never wrap and data cells wrap only at word boundaries", () => {
    const css = readFileSync("src/styles.css", "utf8");
    expect(css).toMatch(/\.step-glyph \{[^}]*white-space: nowrap/);
    expect(css).toMatch(/\.ds-grid dd \{ overflow-wrap: anywhere/);
    expect(css).not.toContain("word-break: break-all");
  });

  // covers web/src/components/wizard/FrontPanel.tsx::FrontPanel
  it("#39 step content precedes the rail in DOM (focus) order", () => {
    const html = rts(<FrontPanel title="t" subtitle={null} rail={<i>RAIL</i>} shortcuts={null} live={null} status={null} next={null}>BODY</FrontPanel>);
    expect(html.indexOf("BODY")).toBeLessThan(html.indexOf("RAIL"));
  });
});
