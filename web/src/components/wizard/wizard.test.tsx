// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
import { renderToString as rts } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { StatusBar } from "../status/StatusBar";
import { ErrorNotice } from "./ErrorNotice";
import { NextActionPanel } from "./NextActionPanel";
import { FrontPanel } from "./FrontPanel";
import { STEP_GUIDE } from "./stepGuide";
import { ShortcutList } from "./ShortcutList";
import { StepRail } from "./StepRail";
import { WizardShell } from "./WizardShell";
import type { RailItem } from "./types";
import { fakeLive, withLive } from "../../state/testLive";
import { closeSession, postWizard, toFailure } from "./wizardApi";
import { CloseSessionView, CLOSE_CONFIRM_TEXT } from "./CloseSession";

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

  it("is a labelled nav with exactly one tab stop, on the current step", () => {
    const html = renderToString(<StepRail rail={rail} />);
    expect(html).toContain('<nav aria-label="Steps"');
    expect(html.match(/tabindex="0"/g)?.length).toBe(1);
    expect(html).toMatch(/<li[^>]*aria-current="step"[^>]*tabindex="0"|<li[^>]*tabindex="0"[^>]*aria-current="step"/);
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

  // frob:ticket 01M6XAASPRSYNWC5K5MH77E8KJ
  it("marks the primary button and Skip with distinct variant classes", () => {
    const f = (): void => undefined;
    const html = renderToString(<NextActionPanel step={rail[1] ?? null} busy={false} canSkip onPrimary={f} onSkip={f} />);
    expect(html).toMatch(/class="btn btn-primary"[^>]*data-variant="primary"/);
    expect(html).toMatch(/class="btn btn-secondary"[^>]*data-variant="secondary"/);
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
    const html = renderToString(withLive(<WizardShell />));
    expect(html).toContain("Loading steps");
    expect(html).toContain("Ctrl+Z");
    expect(html).toContain("Measuring...");
  });

  // frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
  it("lays out the front panel with the do-this card and live trace", () => {
    const html = renderToString(withLive(<WizardShell><p>Step body</p></WizardShell>, fakeLive({ view: { volts: 1.5 } })));
    expect(html).toContain('class="front-panel"');
    expect(html).toContain("<h1>Guided run</h1>");
    expect(html).toContain('aria-label="Live trace"');
    expect(html.indexOf("Step body")).toBeLessThan(html.indexOf('aria-label="Live trace"'));
  });

  it("status bar reflects the shared live feed", () => {
    const html = renderToString(withLive(<WizardShell />, fakeLive({ view: { motion: "creeping" } })));
    expect(html).toContain("Creeping");
  });
});

describe("StepRail description", () => {
  it("shows a plain-language description per step", () => {
    const html = renderToString(<StepRail rail={[item("setup", "Setup", "current")]} />);
    expect(html).toContain("Check the clamps hold the specimen without slipping.");
    expect(html).toContain("(current)");
  });
});

// frob:ticket 01M7230XGWSR1B8D93KW5M4P7D
describe("Close session", () => {
  const noop = (): void => undefined;
  const view = (over: Partial<Parameters<typeof CloseSessionView>[0]> = {}): string => renderToString(
    <CloseSessionView label="Close session" confirming={false} busy={false} failure={null} onAsk={noop} onConfirm={noop} onCancel={noop} {...over} />);

  it("header shell offers Close session", () => {
    const html = renderToString(withLive(<WizardShell />, fakeLive({})));
    expect(html).toContain("Close session");
  });

  it("finished screen offers Start another session", () => {
    const html = renderToString(<NextActionPanel step={null} busy={false} canSkip={false} onPrimary={noop} onSkip={noop}
      finishedActions={<CloseSessionView label="Start another session" confirming={false} busy={false} failure={null} onAsk={noop} onConfirm={noop} onCancel={noop} />} />);
    expect(html).toContain("All steps are finished");
    expect(html).toContain("Start another session");
  });

  it("asks for confirmation and says data is kept", () => {
    expect(view()).not.toContain("alertdialog");
    const html = view({ confirming: true });
    expect(html).toContain("alertdialog");
    expect(html).toContain(CLOSE_CONFIRM_TEXT);
    expect(CLOSE_CONFIRM_TEXT).toContain("stays saved");
  });

  it("closeSession POSTs /api/session/close and reports success", async () => {
    const f = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));
    const r = await closeSession(f);
    expect(r.ok).toBe(true);
    expect(f).toHaveBeenCalledWith("/api/session/close", expect.objectContaining({ method: "POST" }));
  });

  it("closeSession surfaces a problem on refusal", async () => {
    const body = JSON.stringify({ title: "Cannot close", hint: "Wait for the write." });
    const r = await closeSession((() => Promise.resolve(new Response(body, { status: 409 }))));
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.kind).toBe("problem");
  });
});

// frob:ticket 01M7274EKWS410XEGZGFD6HWHK
describe("Finish gate and layout", () => {
  const f = (): void => undefined;
  it("disables Finish as a secondary button with the reason when blocked", () => {
    const html = renderToString(<NextActionPanel step={rail[1] ?? null} busy={false} canSkip onPrimary={f} onSkip={f} finishBlockedWhy="Accept at least 3 points first." />);
    expect(html).toMatch(/<button[^>]*disabled[^>]*btn-secondary|<button[^>]*btn-secondary[^>]*disabled/);
    expect(html).toContain("Accept at least 3 points first.");
    expect(html).not.toContain("btn-primary");
  });
  it("puts the step content between the guide and the next action", () => {
    const html = renderToString(<FrontPanel title="t" subtitle={null} rail={null} shortcuts={null} live={null} status={null}
      guide={<i>GUIDE</i>} next={<i>NEXT</i>} after={<i>AFTER</i>}><i>CARD</i></FrontPanel>);
    const at = (s: string): number => html.indexOf(s);
    expect(at("GUIDE")).toBeLessThan(at("CARD"));
    expect(at("CARD")).toBeLessThan(at("NEXT"));
    expect(at("NEXT")).toBeLessThan(at("AFTER"));
  });
  it("calibration guide mentions the mark step and Accept point", () => {
    const text = (STEP_GUIDE.calibration?.doThis ?? []).join(" ");
    expect(text).toContain("I moved to a new gauge block");
    expect(text).toContain("Accept point (Space)");
  });
});
