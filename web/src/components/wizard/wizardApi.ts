// frob:ticket 01M6X9NXTD91A49K5KE81EQRYA
// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import { getJson, type ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import { err, ok, type Result } from "../../api/result";
import type { Committed, Problem, WizardState } from "./types";

const log = getLogger("wizard.api");

/** Write endpoints the shell can call. */
export type WizardWrite = "wizard/complete" | "wizard/skip" | "wizard/revert" | "undo" | "redo";

/** Hint shown when the server answers 422 with no problem body (usually a web/dist older than the source). */
export const STALE_DIST_HINT = "The web build may be out of date. Rebuild it (cd web && npm run build), restart the app and reload the page.";

/** A failed call: a server problem (with hint) or a transport error. */
export type WizardFailure = { kind: "problem"; problem: Problem } | { kind: "transport"; error: ApiError };

// frob:accept COV001 because="vitest tests exist (wizard.test.tsx, keymap.test.ts) but TypeScript test discovery needs grimble, not installed here"
/** Fetch the rail and current step. */
export async function getWizard(fetchImpl: typeof fetch = fetch): Promise<Result<WizardState, WizardFailure>> {
  const r = await getJson<WizardState>("/api/session/wizard", fetchImpl);
  if (r.ok) return r;
  return err(toFailure(r.error));
}

/** POST a wizard transition (with the `step` it applies to) or undo/redo; returns the committed state. */
export async function postWizard(
  what: WizardWrite,
  fetchImpl: typeof fetch = fetch,
  step?: string,
): Promise<Result<Committed, WizardFailure>> {
  const path = `/api/session/${what}`;
  log.info("write", { path });
  let res: Response;
  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (step !== undefined) headers["Content-Type"] = "application/json";
    res = await fetchImpl(path, { method: "POST", headers, body: step === undefined ? undefined : JSON.stringify({ step }) });
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
  if (error.kind === "http" && error.status === 422) {
    log.warn("422 without a problem body: likely stale web/dist", { body: error.body.slice(0, 120) });
    return { kind: "problem", problem: { type: "", title: "Request rejected", status: 422, detail: "The server rejected this request (HTTP 422).", hint: STALE_DIST_HINT } };
  }
  return { kind: "transport", error };
}

/** POST /api/session/close: closes the open session; its data stays in the session folder. */
export async function closeSession(fetchImpl: typeof fetch = fetch): Promise<Result<null, WizardFailure>> {
  const path = "/api/session/close";
  log.info("closing session", { path });
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
    log.warn("close refused", { path, status: res.status });
    return err(toFailure({ kind: "http", status: res.status, body }));
  }
  log.info("session closed");
  return ok(null);
}
