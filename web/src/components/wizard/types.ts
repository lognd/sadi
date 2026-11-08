// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
/** Wire types for GET /api/session/wizard and the write endpoints (mirror sadi.core.wizard). */

/** Where a step stands on the rail. */
export type StepStatus = "done" | "skipped" | "current" | "locked";

/** One rail entry. */
export interface RailItem {
  id: string;
  title: string;
  phase: string;
  capture: string;
  status: StepStatus;
  needs_device: boolean;
  hint: string;
}

/** Derived wizard position. */
export interface WizardState {
  rail: RailItem[];
  current: string | null;
  anomalies: string[];
}

/** One undoable action. */
export interface HistoryAction {
  kind: string;
  ref: string;
  label: string;
}

/** Undo and redo stacks, oldest first. */
export interface History {
  undo: HistoryAction[];
  redo: HistoryAction[];
}

/** What an accepted write returns. */
export interface Committed {
  seq: number;
  summary: string;
  wizard: WizardState;
  history: History;
}

/** application/problem+json body: `hint` says what to do. */
export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  hint: string;
}
