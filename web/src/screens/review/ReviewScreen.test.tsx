// frob:ticket 01M6W7RARKCF5E5N60RFHNEDX8
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import {
  HistoryList, PointEditor, PointList, ReviewScreen, SAFETY_NOTE, historyLabel, nudgeEdit,
  parseCount, parseInputValue, pointFlags,
} from "./ReviewScreen";
import { describeProblem, editPoint, redo, undo } from "./api";
import { loadReview, runAction, type ReviewData } from "./session";
import type { PointView } from "./types";

const pt = (id: string, over: Partial<PointView> = {}): PointView => ({
  point_id: id, seq: 1, phase: "elastic", excluded: false, inputs: { weights: "3,5" },
  window: { first_raw_seq: 1, last_raw_seq: 9, first_sample: 2, last_sample: 8 }, history: [], settled: true, ...over,
});
const hist = { undo: [{ kind: "point", ref: "p1", label: "exclude p1" }], redo: [] };
const results = { n_points: 1, values: [], pending: ["E"], notes: [], refinement: [] };
const data: ReviewData = { points: [pt("p1"), pt("p2", { excluded: true, forced_early: true })], history: hist, results };

const urlOf = (i: Parameters<typeof fetch>[0]): string => (typeof i === "string" ? i : i instanceof URL ? i.href : i.url);
const json = (b: unknown, status = 200): Response => new Response(JSON.stringify(b), { status });
/** Fake server: records calls; edits/undo succeed, reads return canned data. */
function fake(fail?: Response): { f: typeof fetch; calls: string[] } {
  const calls: string[] = [];
  const f: typeof fetch = (input, init) => {
    const url = urlOf(input);
    calls.push(`${init?.method ?? "GET"} ${url}`);
    if (init?.method === "POST") return Promise.resolve(fail ?? json({ seq: 5, summary: "exclude p1", history: hist }));
    if (url.endsWith("/points")) return Promise.resolve(json(data.points));
    if (url.endsWith("/history")) return Promise.resolve(json(hist));
    return Promise.resolve(json(results));
  };
  return { f, calls };
}

describe("pure helpers", () => {
  it("flags, parsing and labels", () => {
    expect(pointFlags(pt("a"))).toBe("settled");
    expect(pointFlags(pt("a", { settled: false, forced_early: true, excluded: true }))).toBe("forced early, excluded");
    expect(parseInputValue("1.5")).toBe(1.5);
    expect(parseInputValue("3,5")).toBe("3,5");
    expect(parseCount("12")).toBe(12);
    expect(parseCount("-1")).toBeNull();
    expect(historyLabel("Undo", hist.undo)).toBe("Undo: exclude p1");
    expect(historyLabel("Redo", [])).toBe("Redo (nothing to redo)");
  });

  it("nudges one sample and never below zero", () => {
    const w = pt("a").window;
    expect(nudgeEdit("nudge-start-later", w)).toEqual({ op: "set_window", args: { first_sample: 3 } });
    expect(nudgeEdit("nudge-end-earlier", w)).toEqual({ op: "set_window", args: { last_sample: 7 } });
    expect(nudgeEdit("nudge-start-earlier", { ...w, first_sample: 0 })).toBeNull();
    expect(nudgeEdit("accept", w)).toBeNull();
  });

  it("shows problem+json title, detail and hint", () => {
    const body = JSON.stringify({ title: "Bad window", detail: "start after end", hint: "Move the start earlier." });
    const m = describeProblem({ kind: "http", status: 422, body });
    expect(m).toContain("Bad window: start after end");
    expect(m).toContain("Hint: Move the start earlier.");
    expect(describeProblem({ kind: "http", status: 500, body: "boom" })).toContain("HTTP 500");
    expect(describeProblem({ kind: "network", message: "down" })).toContain("down");
  });
});

describe("rendering", () => {
  it("lists points with flags and exclude/include buttons", () => {
    const html = renderToString(<PointList points={data.points} selected="p1" busy={false} onSelect={() => undefined} onEdit={() => undefined} />);
    expect(html).toContain("Exclude p1");
    expect(html).toContain("Include p2");
    expect(html).toContain("forced early, excluded");
    expect(html).toContain('aria-pressed="true"');
  });

  it("renders the editor and history with the data-safety note", () => {
    expect(renderToString(<PointEditor point={pt("p1")} busy={false} onEdit={() => undefined} onInvalid={() => undefined} />))
      .toContain("Apply window");
    const h = renderToString(<HistoryList data={data} />);
    expect(h).toContain("point: exclude p1");
    expect(h).toContain("compensating");
    expect(SAFETY_NOTE).toContain("original captured data is always kept");
  });

  it("renders undo/redo with shortcuts, results and history", () => {
    const html = renderToString(<ReviewScreen initial={data} />);
    expect(html).toContain("Undo: exclude p1 (Ctrl+Z)");
    expect(html).toContain("Redo (nothing to redo) (Ctrl+Y)");
    expect(html).toContain('data-testid="results-panel"');
    expect(html).toContain("Captured points");
  });

  it("renders a loading state without data", () => {
    expect(renderToString(<ReviewScreen />)).toContain("Loading review");
  });
});

describe("actions", () => {
  it("posts the edit, then reloads points, history and results", async () => {
    const { f, calls } = fake();
    const o = await runAction(data, () => editPoint("p1", { op: "exclude", args: {} }, f), f);
    expect(o.error).toBeNull();
    expect(o.note).toBe("exclude p1");
    expect(calls[0]).toBe("POST /api/session/points/p1/edit");
    expect(calls).toContain("GET /api/results");
    expect(calls).toContain("GET /api/session/history");
  });

  it("undo and redo are POSTs", async () => {
    const { f, calls } = fake();
    await undo(f);
    await redo(f);
    expect(calls).toEqual(["POST /api/session/undo", "POST /api/session/redo"]);
  });

  it("keeps the data and shows the hint when the edit is refused", async () => {
    const body = { title: "Bad window", detail: "", hint: "Fix the window.", status: 422, type: "x" };
    const { f, calls } = fake(json(body, 422));
    const o = await runAction(data, () => editPoint("p1", { op: "set_window", args: {} }, f), f);
    expect(o.data).toBe(data);
    expect(o.error).toContain("Hint: Fix the window.");
    expect(calls).toHaveLength(1);
  });

  it("loads without results when recompute is unavailable", async () => {
    const f: typeof fetch = (input) => Promise.resolve(
      urlOf(input).endsWith("/results") ? json({}, 409) : urlOf(input).endsWith("/history") ? json(hist) : json(data.points));
    const l = await loadReview(f);
    expect(l.data?.results).toBeNull();
    const bad = await loadReview(() => Promise.reject(new Error("down")));
    expect(bad.data).toBeNull();
    expect(bad.error).toContain("down");
  });
});
