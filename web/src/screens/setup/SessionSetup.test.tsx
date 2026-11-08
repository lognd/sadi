// frob:ticket 01M6WZX63YFEAYQTPJXE2BTRN2
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SessionSetup, slugFrom, specimenFrom } from "./SessionSetup";
import { failureText } from "./sessionApi";

describe("SessionSetup", () => {
  it("renders the resume list and the new-session form", () => {
    const html = renderToString(<SessionSetup onOpened={() => undefined} />);
    expect(html).toContain("Session setup");
    expect(html).toContain("Create session");
    expect(html).toContain("original is kept");
  });

  it("slugs names and drops blank specimen fields", () => {
    expect(slugFrom("Wire #3 / A")).toBe("wire-3-a");
    expect(slugFrom("   ")).toBe("session");
    expect(specimenFrom({ name: " a ", material: "" })).toEqual({ name: "a" });
  });

  it("describes failures", () => {
    expect(failureText({ kind: "transport", error: { kind: "http", status: 500, body: "" } })).toContain("500");
  });
});
