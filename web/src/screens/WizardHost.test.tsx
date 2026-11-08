// frob:ticket 01M6WZCNF9F9XSPWCKB34JHSD9
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { RailItem } from "../components/wizard/types";
import { App } from "../App";
import { WizardHost, screenFor } from "./WizardHost";

const step = (phase: string, status: RailItem["status"]): RailItem =>
  ({ id: phase, title: phase, phase, capture: "none", status, needs_device: false, hint: "" });
const PHASES = ["setup", "calibration", "tare", "elastic", "plastic", "results", "export"];
const railAt = (cur: number | null): RailItem[] =>
  PHASES.map((p, i) => step(p, cur === null || i < cur ? "done" : i === cur ? "current" : "locked"));

describe("screenFor", () => {
  it("maps each current phase to its screen", () => {
    const want = ["setup", "calibrate", "tare", "elastic", "plastic", "results", "export"];
    want.forEach((w, i) => { expect(screenFor(railAt(i))).toBe(w); });
  });

  it("shows export when every step is finished, and setup for an unknown phase", () => {
    expect(screenFor(railAt(null))).toBe("export");
    expect(screenFor([step("mystery", "current")])).toBe("setup");
  });
});

describe("mounting", () => {
  it("WizardHost renders a loading state until the wizard is fetched", () => {
    expect(renderToString(<WizardHost />)).toContain("Loading steps");
  });

  it("App mounts the wizard host and keeps the Doctor link reachable", () => {
    const html = renderToString(<App />);
    expect(html).toContain("Loading steps");
    expect(html).toContain("Doctor");
    expect(html).toContain("backend: ");
  });
});
