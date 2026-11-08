// frob:ticket 01M6W7RARKCF5E5N60RFHNEDX8
// frob:accept COV001 because="covered by ReviewScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
/** TypeScript mirror of the session edit API (python/sadi/server/schemas.py, sadi/core/wizard.py). */

/** Raw-sample window a point averages over (PointWindow). */
export interface PointWindow {
  first_raw_seq: number;
  last_raw_seq: number;
  first_sample: number;
  last_sample: number;
}

/** A captured point with its edits applied (PointView); settled/forced_early are shown when the server sends them. */
export interface PointView {
  point_id: string;
  seq: number;
  phase: string;
  excluded: boolean;
  inputs: Record<string, unknown>;
  window: PointWindow;
  history: string[];
  settled?: boolean;
  forced_early?: boolean;
}

/** One undoable action (Action). */
export interface HistoryAction {
  kind: string;
  ref: string;
  label: string;
}

/** Undo and redo stacks, oldest first; the last element is what undo/redo would act on. */
export interface HistoryState {
  undo: HistoryAction[];
  redo: HistoryAction[];
}

/** Edit operations the screen can send (EditOp subset for points). */
export type PointEditOp = "exclude" | "include" | "set_window" | "override_input";

/** Body of POST /api/session/points/{id}/edit. */
export interface EditRequest {
  op: PointEditOp;
  args: Record<string, unknown>;
}

/** Response of every accepted write (Committed); the edit is durable before this is returned. */
export interface Committed {
  seq: number;
  summary: string;
  history: HistoryState;
}

/** RFC 7807 body served on every failure. */
export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  hint: string;
}
