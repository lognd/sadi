// frob:ticket 01M6XBSMZHZFQ84PV6PFTS8WZC
// frob:ticket 01M6XBY9FQS5658X6WQ5PCC2QG
// frob:ticket 01M6XCCR9STNBNGX9N4K6N7VQC
// Receiver-qualified calls on typed variables so the call graph resolves them.
import { afterEach, describe, expect, it, vi } from "vitest";
import { getLogger, type Logger } from "./api/log";
import { executeDrawList, type Ctx2D } from "./plots/core/canvas";
import { TraceWindow } from "./plots/live/window";
import { openStream, type SocketLike, type StreamHandle } from "./ws/client";
import { decodeFrame, type TraceFrame } from "./ws/frame";
import { encodeTrace } from "./ws/testframes";

afterEach(() => {
  vi.restoreAllMocks();
});

/** Parameter-typed driver so the call graph resolves Logger.info/warn/error exactly. */
function emitAll(lg: Logger): void {
  lg.info("a");
  lg.warn("b", { k: 1 });
  lg.error("c");
}

/** Parameter-typed driver so the call graph resolves the TraceWindow members exactly. */
function driveWindow(win: TraceWindow, f: TraceFrame): { lo: number[]; hi: number[]; len: number; now0: number; len0: number } {
  win.push(f);
  const s = win.snapshot(2);
  const out = { lo: Array.from(s.lo), hi: Array.from(s.hi), len: win.now(), now0: 0, len0: 0 };
  win.reset();
  out.now0 = win.now();
  out.len0 = win.snapshot(2).x.length;
  return out;
}

/** Parameter-typed driver so the call graph resolves StreamHandle.close and SocketLike.close exactly. */
function closeBoth(hd: StreamHandle, sock: SocketLike): void {
  hd.close();
  sock.close();
}

describe("Logger levels", () => {
  it("info, warn and error reach the matching console method", () => {
    const i = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const w = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const e = vi.spyOn(console, "error").mockImplementation(() => undefined);
    emitAll(getLogger("t"));
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
    const r = decodeFrame(encodeTrace(1, 5, 0.5, { 0: [[1, 2], [3, 4]] }));
    if (!r.ok || r.value.type !== "trace") throw new Error("bad frame");
    const o = driveWindow(new TraceWindow(10, 0), r.value);
    expect(o.len).toBeCloseTo(6);
    expect(o.lo).toEqual([1, 2]);
    expect(o.hi).toEqual([3, 4]);
    expect(o.now0).toBe(0);
    expect(o.len0).toBe(0);
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
    const hd = openStream(
      { url: "ws://x", create: () => sock, timers: { setTimeout: () => 1, clearTimeout: () => undefined } },
      { onState: () => undefined, onFrame: () => undefined, onMessage: () => undefined, onBad: () => undefined },
    );
    closeBoth(hd, sock);
    expect(closed).toBe(2);
  });
});
