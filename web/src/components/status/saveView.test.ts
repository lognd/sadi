// frob:ticket 01M727VHZTQHYABYCT6XTASEM1
import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import { createElement } from "react";
import { saveView } from "./saveView";
import { StatusBar } from "./StatusBar";

const ses = { name: "s", lab: "l", durableSeq: 1 };
const saved = { state: "saved", label: "Saved 12:04:11", pending: 0, hint: "" };

describe("saveView", () => {
  // covers web/src/components/status/saveView.ts::saveView
  it("never says Saved without an open session", () => {
    expect(saveView({ save: saved, session: null })).toEqual({ state: "no-session", text: "No session" });
    expect(saveView({ save: null, session: null }).text).toBe("No session");
  });
  it("shows the backend wording with a session", () => {
    expect(saveView({ save: saved, session: ses }).text).toBe("Saved 12:04:11");
    expect(saveView({ save: { ...saved, state: "saving", label: "Saving...", pending: 2 }, session: ses }).text).toBe("Saving... (2 pending)");
    expect(saveView({ save: { ...saved, state: "not_saved", label: "NOT SAVED" }, session: ses }).state).toBe("not-saved");
  });
  it("never claims saved when the backend is unreachable or unknown", () => {
    expect(saveView({ save: null, session: ses }).state).toBe("unknown");
    expect(saveView({ save: { ...saved, state: "weird" }, session: ses }).state).toBe("unknown");
  });
  // covers web/src/components/status/StatusBar.tsx::StatusBar
  it("status bar renders the same single view", () => {
    const html = renderToString(createElement(StatusBar, { source: "simulated", motion: "settled", signal: "ok", save: saveView({ save: saved, session: null }) }));
    expect(html).toContain("No session");
    expect(html).not.toContain("Saved");
  });
});
