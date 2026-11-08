// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { backoffMs, openStream, type SocketLike, type ConnState } from "./client";
import { decodeFrame } from "./frame";
import { parseMessage } from "./messages";
import { encodeEnvelope, encodeTrace } from "./testframes";

describe("decodeFrame", () => {
  it("decodes a two-channel trace frame", () => {
    const r = decodeFrame(encodeTrace(7, 1.5, 0.5, { 0: [[1, 2], [1, 3]], 3: [[-1, 4], [-1, 4]] }, 1));
    expect(r.ok).toBe(true);
    if (!r.ok || r.value.type !== "trace") throw new Error("expected trace");
    const f = r.value;
    expect([f.seq, f.t0S, f.dtS, f.nPoints, f.stale]).toEqual([7, 1.5, 0.5, 2, true]);
    expect(Array.from(f.channels.get(0)?.max ?? [])).toEqual([1, 3]);
    expect(Array.from(f.channels.get(3)?.min ?? [])).toEqual([-1, 4]);
  });
  it("decodes an envelope", () => {
    const r = decodeFrame(encodeEnvelope(2, 0, '{"v":1}'));
    expect(r.ok && r.value.type === "envelope" && r.value.body).toBe('{"v":1}');
  });
  it("rejects bad input without throwing", () => {
    expect(decodeFrame(new ArrayBuffer(3))).toEqual({ ok: false, error: "short" });
    const bad = encodeTrace(1, 0, 1, { 0: [[1], [1]] });
    new DataView(bad).setUint8(0, 0);
    expect(decodeFrame(bad)).toEqual({ ok: false, error: "magic" });
    const v = encodeTrace(1, 0, 1, { 0: [[1], [1]] });
    new DataView(v).setUint8(4, 9);
    expect(decodeFrame(v)).toEqual({ ok: false, error: "version" });
    const t = encodeTrace(1, 0, 1, { 0: [[1], [1]] });
    new DataView(t).setUint8(5, 9);
    expect(decodeFrame(t)).toEqual({ ok: false, error: "type" });
    expect(decodeFrame(encodeTrace(1, 0, 1, { 0: [[1], [1]] }).slice(0, 70))).toEqual({ ok: false, error: "short" });
  });
});

describe("parseMessage", () => {
  it("parses state, result, stats and unknown kinds", () => {
    const s = parseMessage('{"kind":"state","raw_seq":3,"status":{"state":"creeping","point_index":2,"time_since_load":1.5}}');
    expect(s).toEqual({ ok: true, value: { kind: "state", rawSeq: 3, state: "creeping", pointIndex: 2, timeSinceLoad: 1.5 } });
    const r = parseMessage('{"kind":"result","raw_seq":4,"record":{"point_index":2,"settled":true,"forced_early":false,"window_end":9}}');
    expect(r.ok && r.value.kind === "result" && r.value.windowEnd).toBe(9);
    const st = parseMessage('{"kind":"stats","sent_frames":5,"dropped_frames":1}');
    expect(st.ok && st.value.kind === "stats" && st.value.droppedFrames).toBe(1);
    expect(parseMessage('{"kind":"zzz"}')).toEqual({ ok: true, value: { kind: "other", name: "zzz" } });
  });
  it("rejects garbage", () => {
    expect(parseMessage("nope")).toEqual({ ok: false, error: "not_json" });
    expect(parseMessage("[1]")).toEqual({ ok: false, error: "not_object" });
    expect(parseMessage("{}")).toEqual({ ok: false, error: "no_kind" });
  });
});

const EV = new Event("x") as never;

class FakeSocket implements SocketLike {
  binaryType = "";
  onopen: ((ev: never) => unknown) | null = null;
  onclose: ((ev: never) => unknown) | null = null;
  onerror: ((ev: never) => unknown) | null = null;
  onmessage: ((ev: never) => unknown) | null = null;
  closed = false;
  close(): void { this.closed = true; }
}

describe("openStream", () => {
  it("reconnects with backoff, reports state, routes data, stops on close", () => {
    const socks: FakeSocket[] = [];
    const pending: { fn: () => void; ms: number }[] = [];
    const states: ConnState[] = [];
    let frames = 0;
    const h = openStream(
      { url: "ws://x", create: () => { const s = new FakeSocket(); socks.push(s); return s; },
        timers: { setTimeout: (fn, ms) => { pending.push({ fn, ms }); return pending.length; }, clearTimeout: () => { pending.length = 0; } } },
      { onState: (s) => states.push(s), onFrame: () => { frames++; }, onMessage: () => undefined, onBad: () => undefined },
    );
    const first = socks[0] as FakeSocket;
    first.onopen?.(EV);
    first.onmessage?.(new MessageEvent("message", { data: encodeTrace(1, 0, 1, { 0: [[1], [1]] }) }) as never);
    expect(frames).toBe(1);
    first.onclose?.(EV);
    expect(states.at(-1)).toEqual({ status: "reconnecting", attempt: 2, delayMs: 250 });
    pending.shift()?.fn();
    (socks[1] as FakeSocket).onclose?.(EV);
    expect(states.at(-1)).toEqual({ status: "reconnecting", attempt: 3, delayMs: 500 });
    pending.shift()?.fn();
    (socks[2] as FakeSocket).onopen?.(EV);
    expect(states.at(-1)).toEqual({ status: "open" });
    h.close();
    expect((socks[2] as FakeSocket).closed).toBe(true);
    expect(states.at(-1)).toEqual({ status: "closed" });
  });
  it("caps the backoff", () => {
    expect(backoffMs(1)).toBe(250);
    expect(backoffMs(20)).toBe(8000);
  });
});
