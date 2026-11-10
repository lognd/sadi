// frob:ticket 01M727VHZTQHYABYCT6XTASEM1
import type { BackendFacts } from "../instrument/useBackendFacts";

/** What the one save indicator shows: display text plus a coarse state for styling and tests. */
export interface SaveView {
  readonly state: "no-session" | "unknown" | "saved" | "saving" | "not-saved";
  readonly text: string;
}

/** The single source of truth for the save indicator: never says Saved without an open session and a backend "saved" answer. */
export function saveView(facts: Pick<BackendFacts, "save" | "session">): SaveView {
  if (facts.session === null) return { state: "no-session", text: "No session" };
  const s = facts.save;
  if (s === null) return { state: "unknown", text: "Save status unknown" };
  const pending = s.pending > 0 ? ` (${String(s.pending)} pending)` : "";
  if (s.state === "saved") return { state: "saved", text: `${s.label || "Saved"}${pending}` };
  if (s.state === "saving") return { state: "saving", text: `${s.label || "Saving..."}${pending}` };
  if (s.state === "not_saved") return { state: "not-saved", text: s.label || "NOT SAVED" };
  return { state: "unknown", text: "Save status unknown" };
}
