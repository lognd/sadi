// frob:ticket 01M72YKEWHJJXEBBV7XDP5Z31J
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { problemText, type PostError } from "./api";

const http = (status: number): PostError => ({
  kind: "http",
  status,
  body: "",
  problem: { type: "urn:sadi:error:store:stalled", title: "stalled", detail: "d", hint: "Disk is not responding." },
});

describe("problemText for 5xx capture", () => {
  it("says the outcome is uncertain, not refused", () => {
    const t = problemText(http(503), "Capture");
    expect(t).toMatch(/not confirmed/i);
    expect(t).not.toMatch(/refused/i);
  });
  it("keeps the hint for 4xx and for non-capture writes", () => {
    expect(problemText(http(409), "Capture")).toBe("Capture refused. Disk is not responding.");
    expect(problemText(http(503), "Load change")).toBe("Load change refused. Disk is not responding.");
  });
});
