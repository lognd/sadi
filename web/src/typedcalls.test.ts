// frob:ticket ~FTS8WZC
// Receiver-qualified calls on typed variables so the call graph resolves them.
import { afterEach, describe, expect, it, vi } from "vitest";
import { getLogger, type Logger } from "./api/log";
import { executeDrawList, type Ctx2D } from "./plots/core/canvas";
import { TraceWindow } from "./plots/live/window";
import { openStream, type SocketLike, type StreamHandle } from "./ws/client";
import { decodeFrame } from "./ws/frame";
import { encodeTrace } from "./ws/testframes";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Logger levels", () => {
  it("info, warn and error reach the matching console method", () => {
    const i = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const w = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const e = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const lg: Logger = getLogger("t");
    lg.info("a");
    lg.warn("b", { k: 1 });
    lg.error("c");
    expect(i).toHaveBeenCalledWith("[t] a", {});
    expect(w).toHaveBeenCalledWith("[t] b", { k: 1 });
    expect(e).toHaveBeenCalledWith("[t] c", {});
  });
});

describe("Ctx2D.rotate", () => {
  it("is invoked through the typed context by a rotated text op", () => {
    const calls: string[] = [];
    const base = {
      fillStyle: "", strokeStyle: "", lineWidth: 1, globalAlpha: 1, font: "",
      textAlign: "left", textBaseline: "alphabetic",
    };
    const ctx: Ctx2D = new Proxy(base, {
      get: (t, p: string) => (p in t ? (t as Record<string, unknown>)[p] : (...a: unknown[]) => { calls.push(`${p}:${a.join(",")}`); }),
      set: (t, p: string, v: unknown) => { (t as Record<string, unknown>)[p] = v; return true; },
    }) as unknown as Ctx2D;
    ctx.rotate(0.5);
    executeDrawList(ctx, [], "sans");
    expect(calls).toContain("rotate:0.5");
  });
});

describe("TraceWindow", () => {
  it("push, now, snapshot and reset", () => {
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    vi.spyOn(console, "debug").mockImplementation(() => undefined);
    const win: TraceWindow = new TraceWindow(10, 0);
    const r = decodeFrame(encodeTrace(1, 5, 0.5, { 0: [[1, 2], [3, 4]] }));
    if (!r.ok || r.value.type !== "trace") throw new Error("bad frame");
    win.push(r.value);
    expect(win.now).toBeCloseTo(6);
    const s = win.snapshot(2);
    expect(Array.from(s.lo)).toEqual([1, 2]);
    expect(Array.from(s.hi)).toEqual([3, 4]);
    win.reset();
    expect(win.now).toBe(0);
    expect(win.snapshot(2).x.length).toBe(0);
  });
});

describe("close", () => {
  it("StreamHandle.close closes the SocketLike", () => {
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    let closed = 0;
    const sock: SocketLike = {
      binaryType: "", onopen: null, onclose: null, onerror: null, onmessage: null,
      close(): void { closed++; },
    };
    const hd: StreamHandle = openStream(
      { url: "ws://x", create: () => sock, timers: { setTimeout: () => 1, clearTimeout: () => undefined } },
      { onState: () => undefined, onFrame: () => undefined, onMessage: () => undefined, onBad: () => undefined },
    );
    hd.close();
    sock.close();
    expect(closed).toBe(2);
  });
});
