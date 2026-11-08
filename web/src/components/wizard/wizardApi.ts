// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import { getJson, type ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import { err, ok, type Result } from "../../api/result";
import type { Committed, Problem, WizardState } from "./types";

const log = getLogger("wizard.api");

/** Write endpoints the shell can call. */
export type WizardWrite = "wizard/complete" | "wizard/skip" | "wizard/revert" | "undo" | "redo";

/** A failed call: a server problem (with hint) or a transport error. */
export type WizardFailure = { kind: "problem"; problem: Problem } | { kind: "transport"; error: ApiError };

// frob:accept COV001 because="vitest tests exist (wizard.test.tsx, keymap.test.ts) but TypeScript test discovery needs grimble, not installed here"
/** Fetch the rail and current step. */
export async function getWizard(fetchImpl: typeof fetch = fetch): Promise<Result<WizardState, WizardFailure>> {
  const r = await getJson<WizardState>("/api/session/wizard", fetchImpl);
  if (r.ok) return r;
  return err(toFailure(r.error));
}

/** POST a wizard transition or undo/redo; returns the committed state. */
export async function postWizard(
  what: WizardWrite,
  fetchImpl: typeof fetch = fetch,
): Promise<Result<Committed, WizardFailure>> {
  const path = `/api/session/${what}`;
  log.info("write", { path });
  let res: Response;
  try {
    res = await fetchImpl(path, { method: "POST", headers: { Accept: "application/json" } });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    log.error("network failure", { path, message });
    return err({ kind: "transport", error: { kind: "network", message } });
  }
  if (!res.ok) {
    const body = await res.text();
    log.warn("write refused", { path, status: res.status });
    return err(toFailure({ kind: "http", status: res.status, body }));
  }
  return ok((await res.json()) as Committed);
}

/** Parse an http error body as a problem when possible, else keep the transport error. */
export function toFailure(error: ApiError): WizardFailure {
  if (error.kind === "http") {
    try {
      const p = JSON.parse(error.body) as Partial<Problem>;
      if (typeof p.title === "string" && typeof p.hint === "string") {
        return { kind: "problem", problem: { type: "", detail: "", status: error.status, ...p } as Problem };
      }
    } catch {
      log.debug("error body is not a problem", { status: error.status });
    }
  }
  return { kind: "transport", error };
}
