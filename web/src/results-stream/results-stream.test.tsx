// frob:ticket 01M6W7RB0GPGHTABW7P4XEGRNJ
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import { connectResults, type Subscribe } from "./useResultsStream";
import { StreamedValue } from "./StreamedValue";
import { EMPTY_STATE, type StreamState } from "./store";

const env = (key: string, dv: number, rv: number, state: string, progress = 0, value: unknown = 1): string =>
  JSON.stringify({ protocol_version: 1, key, data_version: dv, result_version: rv, state, progress, value });

function mock(): { sub: Subscribe; push: (t: string) => void; states: StreamState[] } {
  let cb: (t: string) => void = () => undefined;
  const states: StreamState[] = [];
  const sub: Subscribe = (f) => { cb = f; return () => undefined; };
  connectResults(sub, (s) => states.push(s));
  return { sub, push: (t) => { cb(t); }, states };
}
const last = (m: { states: StreamState[] }): StreamState => m.states[m.states.length - 1] ?? EMPTY_STATE;
const html = (s: StreamState): string => renderToString(<StreamedValue state={s} name="E" format={(v) => `E=${String(v)}`} />);

describe("results stream client", () => {
  it("shows pending before any envelope", () => {
    expect(html(EMPTY_STATE)).toContain("pending");
  });

  it("renders a current analytic value with no marker", () => {
    const m = mock();
    m.push(env("E", 1, 1, "analytic", 0, 70));
    const h = html(last(m));
    expect(h).toContain("E=70");
    expect(h).not.toContain("stale-marker");
    expect(h).not.toContain("refine-progress");
  });

  it("shows tightening progress while refining", () => {
    const m = mock();
    m.push(env("E", 1, 1, "analytic"));
    m.push(env("E", 1, 2, "refining", 0.25));
    expect(html(last(m))).toContain('value="25"');
    m.push(env("E", 1, 3, "refining", 0.75));
    expect(html(last(m))).toContain('value="75"');
    m.push(env("E", 1, 4, "final", 1));
    expect(html(last(m))).not.toContain("refine-progress");
  });

  it("marks a value stale when the server says so", () => {
    const m = mock();
    m.push(env("E", 1, 1, "analytic"));
    m.push(env("E", 1, 2, "stale"));
    expect(html(last(m))).toContain("stale-marker");
  });

  it("marks a value stale when another key has newer data, never unmarked", () => {
    const m = mock();
    m.push(env("E", 1, 1, "final", 1));
    m.push(env("slope", 2, 1, "analytic"));
    const s = last(m);
    expect(html(s)).toContain("stale-marker");
    expect(html(s)).not.toContain("refine-progress");
  });

  it("suppresses progress on a lagging refining value", () => {
    const m = mock();
    m.push(env("E", 1, 1, "refining", 0.5));
    m.push(env("slope", 2, 1, "analytic"));
    const h = html(last(m));
    expect(h).toContain("stale-marker");
    expect(h).not.toContain("refine-progress");
  });

  it("drops out-of-order and malformed envelopes", () => {
    const m = mock();
    m.push(env("E", 1, 5, "analytic", 0, 5));
    m.push(env("E", 1, 4, "analytic", 0, 4));
    m.push("not json");
    m.push(JSON.stringify({ protocol_version: 2, key: "E" }));
    expect(m.states).toHaveLength(1);
    expect(html(last(m))).toContain("E=5");
  });
});
