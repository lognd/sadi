// frob:ticket 01M6X9NXTD91A49K5KE81EQRYA
// frob:ticket 01M6W7RARKCF5E5N60RFHNEDX8
// frob:ticket 01M6X9Y0CWQ6YRMDT8QF5JD036
// frob:accept COV001 because="covered by ReviewScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { SyntheticBanner } from "../../components/provenance/SyntheticBanner";
import type * as React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { getLogger } from "../../api/log";
import { ResultsPanel } from "../../components/results/ResultsPanel";
import { useKeyCapture } from "../../keys/useKeyCapture";
import type { KeyAction } from "../../keys/keymap";
import { editPoint, redo, undo } from "./api";
import { loadReview, runAction, type ReviewData } from "./session";
import type { EditRequest, HistoryAction, PointView, PointWindow } from "./types";

const log = getLogger("screens.review");

/** Plain-language data-safety note shown on the screen. */
export const SAFETY_NOTE =
  "Nothing is deleted. Every edit and every undo is recorded as a new compensating edit, and the original captured data is always kept.";

/** Capture-quality flags for a point, e.g. "settled" or "forced early". */
export function pointFlags(p: PointView): string {
  const flags: string[] = [];
  if (p.settled === true) flags.push("settled");
  if (p.forced_early === true) flags.push("forced early");
  if (p.excluded) flags.push("excluded");
  return flags.length ? flags.join(", ") : "none";
}

/** Shorten a long point id (UUID) to its first 8 characters for display; short ids pass through. */
export function shortId(id: string): string {
  return id.length > 12 ? id.slice(0, 8) : id;
}

/** Short text for one input value. */
export function inputText(v: unknown): string {
  return typeof v === "string" ? v : JSON.stringify(v);
}

/** Parse relabel text: a finite number becomes a number, anything else stays text. */
export function parseInputValue(text: string): unknown {
  const t = text.trim();
  const n = Number(t);
  return t !== "" && Number.isFinite(n) ? n : t;
}

/** Parse a non-negative integer field; null when invalid. */
export function parseCount(text: string): number | null {
  const t = text.trim();
  return /^\d+$/.test(t) ? Number(t) : null;
}

/** Edit request for a nudge key on a window, or null when the key is not a nudge or would go below zero. */
export function nudgeEdit(a: KeyAction, w: PointWindow): EditRequest | null {
  const step: Partial<Record<KeyAction, [keyof PointWindow, number]>> = {
    "nudge-start-earlier": ["first_sample", -1],
    "nudge-start-later": ["first_sample", 1],
    "nudge-end-earlier": ["last_sample", -1],
    "nudge-end-later": ["last_sample", 1],
  };
  const s = step[a];
  if (!s) return null;
  const next = w[s[0]] + s[1];
  if (next < 0) return null;
  return { op: "set_window", args: { [s[0]]: next } };
}

/** Label for the next undo or redo, e.g. "Undo: exclude p1", or a disabled hint. */
export function historyLabel(verb: "Undo" | "Redo", stack: readonly HistoryAction[]): string {
  const top = stack.at(-1);
  return top ? `${verb}: ${top.label}` : `${verb} (nothing to ${verb.toLowerCase()})`;
}

/** Visible undo/redo history; undo/redo are new compensating edits, never deletions. */
export function HistoryList({ data }: { data: ReviewData }) {
  const { undo: u, redo: r } = data.history;
  return (
    <section aria-label="History" data-testid="history">
      <h3>History</h3>
      <p>{SAFETY_NOTE}</p>
      {u.length === 0 && r.length === 0 ? <p>No actions yet.</p> : null}
      <ol aria-label="Done actions">
        {u.map((a, i) => <li key={`u${String(i)}`}>{`${a.kind}: ${a.label}`}</li>)}
      </ol>
      {r.length > 0 ? (
        <ol aria-label="Undone actions (can be redone)">
          {r.map((a, i) => <li key={`r${String(i)}`}>{`${a.kind}: ${a.label} (undone)`}</li>)}
        </ol>
      ) : null}
    </section>
  );
}

/** Editor for the selected point: window fields and input relabel; props only. */
export function PointEditor(props: {
  point: PointView;
  busy: boolean;
  onEdit: (req: EditRequest) => void;
  onInvalid: (msg: string) => void;
}) {
  const { point: p, busy, onEdit, onInvalid } = props;
  const w = p.window;
  const [win, setWin] = useState({
    first_raw_seq: String(w.first_raw_seq), last_raw_seq: String(w.last_raw_seq),
    first_sample: String(w.first_sample), last_sample: String(w.last_sample),
  });
  const keys = Object.keys(p.inputs);
  const [key, setKey] = useState(keys[0] ?? "");
  const [val, setVal] = useState("");
  const applyWindow = (): void => {
    const parsed = {
      first_raw_seq: parseCount(win.first_raw_seq), last_raw_seq: parseCount(win.last_raw_seq),
      first_sample: parseCount(win.first_sample), last_sample: parseCount(win.last_sample),
    };
    if (Object.values(parsed).some((v) => v === null)) {
      log.warn("invalid window fields rejected", { point: p.point_id });
      onInvalid("Window fields must be whole numbers, zero or more.");
      return;
    }
    onEdit({ op: "set_window", args: parsed });
  };
  const applyInput = (): void => {
    if (key === "" || val.trim() === "") {
      onInvalid("Choose an input and enter its new value.");
      return;
    }
    onEdit({ op: "override_input", args: { [key]: parseInputValue(val) } });
  };
  const field = (name: keyof typeof win, label: string) => (
    <label key={name}>
      {`${label} `}
      <input type="text" inputMode="numeric" value={win[name]}
             onChange={(e) => { setWin({ ...win, [name]: e.target.value }); }} />
    </label>
  );
  return (
    <section aria-label={`Edit point ${p.point_id}`} data-testid="point-editor">
      <h3>{`Edit point ${p.point_id}`}</h3>
      <fieldset>
        <legend>Averaging window (raw sequence and sample)</legend>
        {field("first_raw_seq", "First raw seq")}
        {field("last_raw_seq", "Last raw seq")}
        {field("first_sample", "First sample")}
        {field("last_sample", "Last sample")}
        <button type="button" disabled={busy} onClick={applyWindow}>Apply window</button>
        <p>Keys [ and ] move the start, { } move the end, one sample at a time.</p>
      </fieldset>
      <fieldset>
        <legend>Relabel an input (for example weights)</legend>
        <label>
          {"Input "}
          <select value={key} onChange={(e) => { setKey(e.target.value); }}>
            {keys.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </label>
        <label>
          {"New value "}
          <input type="text" value={val} onChange={(e) => { setVal(e.target.value); }} />
        </label>
        <button type="button" disabled={busy} onClick={applyInput}>Apply input</button>
      </fieldset>
    </section>
  );
}

/** Index of the row action (0 = Edit, 1 = Exclude/Include) after an arrow key, or null for other keys; clamps at the ends. */
export function rowActionAfterKey(current: number, key: string): number | null {
  if (key === "ArrowRight") return Math.min(current + 1, 1);
  if (key === "ArrowLeft") return Math.max(current - 1, 0);
  return null;
}

/** Point table with flags and one roving Tab stop per row (Left/Right switch Edit and Exclude); props only. */
export function PointList(props: {
  points: readonly PointView[];
  selected: string | null;
  busy: boolean;
  onSelect: (id: string) => void;
  onEdit: (id: string, req: EditRequest) => void;
}) {
  const { points, selected, busy, onSelect, onEdit } = props;
  // Roving tabindex: one Tab stop per row; the remembered action per row holds tabIndex 0.
  const [active, setActive] = useState<Record<string, number>>({});
  const onRowKey = (id: string, e: React.KeyboardEvent<HTMLElement>): void => {
    const next = rowActionAfterKey(active[id] ?? 0, e.key);
    if (next === null) return;
    e.preventDefault();
    setActive((m) => ({ ...m, [id]: next }));
    const buttons = e.currentTarget.querySelectorAll("button");
    buttons[next]?.focus();
  };
  const tab = (id: string, i: number): number => ((active[id] ?? 0) === i ? 0 : -1);
  if (points.length === 0) return <p>No points captured yet.</p>;
  return (
    <>
    <a href="#next-action" data-testid="skip-to-finish">Skip to Finish</a>
    <div className="table-scroll" data-testid="points-scroll" style={{ overflowX: "auto", maxWidth: "100%" }}>
    <table aria-label="Captured points">
      <thead>
        <tr><th scope="col">Point</th><th scope="col">Phase</th><th scope="col">Flags</th>
          <th scope="col">Inputs</th><th scope="col">Edits</th><th scope="col">Actions</th></tr>
      </thead>
      <tbody>
        {points.map((p) => (
          <tr key={p.point_id} data-testid={`point-${p.point_id}`} aria-selected={p.point_id === selected}>
            <th scope="row" title={p.point_id}>{`#${String(p.seq)} ${shortId(p.point_id)}`}</th>
            <td>{p.phase}</td>
            <td>{pointFlags(p)}</td>
            <td>{Object.entries(p.inputs).map(([k, v]) => `${k}=${inputText(v)}`).join("; ")}</td>
            <td>{String(p.history.length)}</td>
            <td>
             <div role="group" aria-label={`Actions for point ${String(p.seq)}`}
                  onKeyDown={(e) => { onRowKey(p.point_id, e); }}>
              <button type="button" tabIndex={tab(p.point_id, 0)} aria-pressed={p.point_id === selected}
                      onClick={() => { onSelect(p.point_id); }}>
                {`Edit point ${String(p.seq)}`}
              </button>
              <button type="button" tabIndex={tab(p.point_id, 1)} disabled={busy}
                      onClick={() => { onEdit(p.point_id, { op: p.excluded ? "include" : "exclude", args: {} }); }}>
                {`${p.excluded ? "Include" : "Exclude"} point ${String(p.seq)}`}
              </button>
             </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
    </>
  );
}

/** Review screen: edit captured points, nudge windows, undo/redo, results recomputed from raw after each edit. */
export function ReviewScreen({ initial, fetchImpl }: { initial?: ReviewData; fetchImpl?: typeof fetch }) {
  const [data, setData] = useState<ReviewData | null>(initial ?? null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const latest = useRef(data);
  latest.current = data;

  useEffect(() => {
    if (initial) return;
    void loadReview(fetchImpl).then((l) => {
      log.info("review loaded", { ok: l.data !== null });
      setData(l.data);
      setError(l.error);
    });
  }, [initial, fetchImpl]);

  const act = useCallback((write: () => ReturnType<typeof undo>): void => {
    const prev = latest.current;
    if (prev === null) return;
    setBusy(true);
    void runAction(prev, write, fetchImpl).then((o) => {
      setData(o.data);
      setError(o.error);
      setNote(o.note);
      setBusy(false);
    });
  }, [fetchImpl]);

  const doEdit = useCallback((id: string, req: EditRequest): void => {
    log.info("edit requested", { id, op: req.op });
    act(() => editPoint(id, req, fetchImpl));
  }, [act, fetchImpl]);
  const doUndo = useCallback((): void => { log.info("undo requested"); act(() => undo(fetchImpl)); }, [act, fetchImpl]);
  const doRedo = useCallback((): void => { log.info("redo requested"); act(() => redo(fetchImpl)); }, [act, fetchImpl]);

  const point = data?.points.find((p) => p.point_id === selected) ?? null;
  useKeyCapture((a) => {
    if (busy || data === null) return;
    if (a === "undo" && data.history.undo.length > 0) { doUndo(); return; }
    if (a === "redo" && data.history.redo.length > 0) { doRedo(); return; }
    if (a === "cancel") { setSelected(null); return; }
    if (point) {
      const req = nudgeEdit(a, point.window);
      if (req) doEdit(point.point_id, req);
    }
  }, point !== null);

  if (data === null) {
    return (
      <section aria-label="Review">
        {error ? <p role="alert">{error}</p> : <p role="status">Loading review...</p>}
      </section>
    );
  }
  return (
    <section aria-label="Review" aria-busy={busy}>
      <h1>Review</h1>
      <p>Your results are shown first; the captured points below let you correct them.</p>
      <SyntheticBanner />
      {data.results ? <ResultsPanel results={data.results} /> : <p>Results are not available yet.</p>}
      <p>{SAFETY_NOTE}</p>
      <div>
        <button type="button" disabled={busy || data.history.undo.length === 0} aria-keyshortcuts="Control+Z"
                onClick={doUndo}>
          {`${historyLabel("Undo", data.history.undo)} (Ctrl+Z)`}
        </button>
        <button type="button" disabled={busy || data.history.redo.length === 0} aria-keyshortcuts="Control+Y"
                onClick={doRedo}>
          {`${historyLabel("Redo", data.history.redo)} (Ctrl+Y)`}
        </button>
      </div>
      {error ? <p role="alert" data-testid="review-error">{error}</p> : null}
      {note ? <p role="status" data-testid="review-note">{`Saved: ${note}. Results recomputed from the raw data.`}</p> : null}
      <PointList points={data.points} selected={selected} busy={busy} onSelect={setSelected} onEdit={doEdit} />
      {point ? (
        <PointEditor key={`${point.point_id}-${String(point.history.length)}`} point={point} busy={busy}
                     onEdit={(req) => { doEdit(point.point_id, req); }}
                     onInvalid={(m) => { setError(m); }} />
      ) : null}
      <HistoryList data={data} />
    </section>
  );
}
