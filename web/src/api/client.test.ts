import { describe, expect, it } from "vitest";
import { getHealth } from "./client";

const json = (body: unknown, status = 200): typeof fetch =>
  () => Promise.resolve(new Response(JSON.stringify(body), { status }));

describe("getHealth", () => {
  it("returns the parsed payload on 200", async () => {
    const r = await getHealth(json({ status: "ok", version: "1" }));
    expect(r).toEqual({ ok: true, value: { status: "ok", version: "1" } });
  });

  it("maps non-2xx to an http error", async () => {
    const r = await getHealth(json({ detail: "x" }, 500));
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatchObject({ kind: "http", status: 500 });
  });

  it("maps a thrown fetch to a network error", async () => {
    const r = await getHealth(() => Promise.reject(new Error("down")));
    expect(r).toEqual({ ok: false, error: { kind: "network", message: "down" } });
  });
});
