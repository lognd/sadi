// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import { renderToString as rts } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { StatusBar } from "../status/StatusBar";
import { ErrorNotice } from "./ErrorNotice";
import { NextActionPanel } from "./NextActionPanel";
import { ShortcutList } from "./ShortcutList";
import { StepRail } from "./StepRail";
import { WizardShell } from "./WizardShell";
import type { RailItem } from "./types";
import { postWizard, toFailure } from "./wizardApi";

/** Render and drop React text-boundary comments. */
const renderToString = (el: React.JSX.Element): string => rts(el).replaceAll("<!-- -->", "");

const item = (id: string, title: string, status: RailItem["status"], hint = ""): RailItem =>
  ({ id, title, phase: "setup", capture: "none", status, needs_device: false, hint });
const rail = [item("setup", "Setup", "done"), item("tare", "Tare", "current", "Unload the specimen."),
  item("elastic", "Elastic", "locked"), item("plastic", "Plastic", "skipped", "reused")];

describe("StepRail", () => {
  it("shows glyph and word per step and marks current", () => {
    const html = renderToString(<StepRail rail={rail} />);
    expect(html).toContain("[x]");
    expect(html).toContain("[&gt;]");
    expect(html).toContain("(upcoming)");
    expect(html).toContain("(skipped)");
    expect(html).toContain('aria-current="step"');
  });
});

describe("NextActionPanel", () => {
  it("shows the hint and primary button, or finished", () => {
    const f = (): void => undefined;
    const html = renderToString(<NextActionPanel step={rail[1] ?? null} busy={false} canSkip onPrimary={f} onSkip={f} />);
    expect(html).toContain("Unload the specimen.");
    expect(html).toContain("Finish Tare");
    expect(renderToString(<NextActionPanel step={null} busy={false} canSkip={false} onPrimary={f} onSkip={f} />))
      .toContain("All steps are finished");
  });
});

describe("StatusBar", () => {
  it("renders words for all indicators", () => {
    const html = renderToString(<StatusBar source="simulated" motion="creeping" signal="saturated" savedAt="12:04:11" />);
    expect(html).toContain("Simulated");
    expect(html).toContain("Creeping");
    expect(html).toContain("SATURATED");
    expect(html).toContain("Saved 12:04:11");
  });
});

describe("ErrorNotice", () => {
  it("renders the what-to-do hint", () => {
    const failure = toFailure({ kind: "http", status: 409, body: JSON.stringify(
      { type: "t", title: "gated", status: 409, detail: "Blocked.", hint: "Complete the earlier step." }) });
    const html = renderToString(<ErrorNotice failure={failure} />);
    expect(html).toContain("Blocked.");
    expect(html).toContain("What to do: Complete the earlier step.");
  });
  it("hints at a stale web build on a bare 422", () => {
    const failure = toFailure({ kind: "http", status: 422, body: "{\"detail\":[{\"loc\":[\"body\",\"step\"]}]}" });
    expect(failure.kind).toBe("problem");
    expect(renderToString(<ErrorNotice failure={failure} />)).toContain("npm run build");
  });
  it("falls back to a transport message for non-problem bodies", () => {
    const failure = toFailure({ kind: "http", status: 500, body: "boom" });
    expect(failure.kind).toBe("transport");
    expect(renderToString(<ErrorNotice failure={failure} />)).toContain("Could not reach");
  });
});

describe("ShortcutList", () => {
  it("lists shortcuts on screen", () => {
    expect(renderToString(<ShortcutList />)).toContain("Ctrl+Z");
  });
});

describe("postWizard", () => {
  it("returns the problem on a refused write", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ title: "nothing to undo", hint: "Nothing to undo", status: 409 }), { status: 409 }));
    const r = await postWizard("undo", fetchImpl);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.kind).toBe("problem");
  });
  it("sends the step as a JSON body for wizard transitions", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ seq: 1 }), { status: 200 }));
    await postWizard("wizard/skip", fetchImpl, "setup");
    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect(init.body).toBe(JSON.stringify({ step: "setup" }));
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });
  it("reports network failure", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error("down"));
    const r = await postWizard("redo", fetchImpl);
    expect(!r.ok && r.error.kind).toBe("transport");
  });
});

describe("WizardShell", () => {
  it("renders loading rail, shortcuts and status bar on first paint", () => {
    const html = renderToString(<WizardShell status={{ source: "connected", motion: "unknown", signal: "ok" }} />);
    expect(html).toContain("Loading steps");
    expect(html).toContain("Ctrl+Z");
    expect(html).toContain("Measuring...");
  });
});
