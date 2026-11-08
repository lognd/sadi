// frob:ticket 01M6WMGMJE0WEXXNQ3AD754A8M
import { describe, expect, it } from "vitest";
import { refitModulus } from "./refit";

const fit = { first: 1, last: 4, modulusMpa: 1, interceptMpa: 0, eGpa: 71, eU95Gpa: 2, r2: 0.99, lowR2: false };

describe("refitModulus", () => {
  it("POSTs the window and returns the fit", async () => {
    let seen: { url: string; init?: RequestInit } | null = null;
    const f: typeof fetch = (url, init) => {
      seen = { url: typeof url === "string" ? url : "?", init };
      return Promise.resolve(new Response(JSON.stringify(fit)));
    };
    const r = await refitModulus({ first: 1, last: 4 }, f);
    expect(r).toEqual({ ok: true, value: fit });
    expect(seen).toMatchObject({ url: "/api/stress-strain/fit", init: { method: "POST", body: '{"first":1,"last":4}' } });
  });

  it("maps http and network failures to errors", async () => {
    const h = await refitModulus({ first: 0, last: 3 }, () => Promise.resolve(new Response("bad", { status: 422 })));
    expect(h).toEqual({ ok: false, error: { kind: "http", status: 422, body: "bad" } });
    const n = await refitModulus({ first: 0, last: 3 }, () => Promise.reject(new Error("down")));
    expect(n).toEqual({ ok: false, error: { kind: "network", message: "down" } });
  });
});
