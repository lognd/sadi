// frob:ticket 01M6WW75K1WH5X7NAKE008D0RA
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import type { ConnState, SocketLike } from "../ws/client";
import { encodeEnvelope, encodeTrace } from "../ws/testframes";
import { connectResults } from "./useResultsStream";
import { EMPTY_STATE, type StreamState } from "./store";
import { wsSubscribe } from "./wsSubscribe";

class FakeSocket implements SocketLike {
  binaryType = "blob";
  onopen: SocketLike["onopen"] = null;
  onclose: SocketLike["onclose"] = null;
  onerror: SocketLike["onerror"] = null;
  onmessage: SocketLike["onmessage"] = null;
  closed = false;
  close(): void { this.closed = true; }
  send(data: ArrayBuffer | string): void { this.onmessage?.(new MessageEvent("message", { data }) as never); }
}

const EV = undefined as never;
const env = (key: string, dv: number, rv: number): string =>
  JSON.stringify({ protocol_version: 1, key, data_version: dv, result_version: rv, state: "final", progress: 0, value: rv });

function setup() {
  const socks: FakeSocket[] = [];
  const pending: (() => void)[] = [];
  const conn: ConnState[] = [];
  const sub = wsSubscribe({
    url: "ws://x",
    create: () => { const s = new FakeSocket(); socks.push(s); return s; },
    timers: { setTimeout: (fn) => { pending.push(fn); return pending.length; }, clearTimeout: () => { pending.length = 0; } },
    onConn: (s) => conn.push(s),
  });
  return { socks, pending, conn, sub };
}

describe("wsSubscribe", () => {
  it("forwards envelope frames only, ignoring trace frames and junk", () => {
    const { socks, sub } = setup();
    const texts: string[] = [];
    sub((t) => texts.push(t));
    const s = socks[0] as FakeSocket;
    expect(s.binaryType).toBe("arraybuffer");
    s.send(encodeTrace(1, 0, 1, { 0: [[1], [1]] }));
    s.send(new ArrayBuffer(3));
    s.send(encodeEnvelope(2, 0, env("E", 1, 1)));
    expect(texts).toEqual([env("E", 1, 1)]);
  });

  it("survives reconnects: replays are dropped, newer results apply, unsubscribe closes", () => {
    const { socks, pending, conn, sub } = setup();
    let state: StreamState = EMPTY_STATE;
    const off = connectResults(sub, (s) => { state = s; });
    (socks[0] as FakeSocket).onopen?.(EV);
    (socks[0] as FakeSocket).send(encodeEnvelope(1, 0, env("E", 1, 2)));
    (socks[0] as FakeSocket).onclose?.(EV);
    expect(conn.at(-1)?.status).toBe("reconnecting");
    pending.shift()?.();
    const s1 = socks[1] as FakeSocket;
    s1.onopen?.(EV);
    s1.send(encodeEnvelope(2, 0, env("E", 1, 1))); // older replay
    expect(state.byKey["E"]?.value).toBe(2);
    s1.send(encodeEnvelope(3, 0, env("E", 1, 3)));
    expect(state.byKey["E"]?.value).toBe(3);
    off();
    expect(s1.closed).toBe(true);
    expect(conn.at(-1)).toEqual({ status: "closed" });
    expect(pending.length).toBe(0);
  });
});
