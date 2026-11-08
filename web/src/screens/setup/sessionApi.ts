// frob:ticket 01M6WZX63YFEAYQTPJXE2BTRN2
import { getJson } from "../../api/client";
import { getLogger } from "../../api/log";
import { err, ok, type Result } from "../../api/result";
import type { components } from "../../api/schema";
import { toFailure, type WizardFailure } from "../../components/wizard/wizardApi";

const log = getLogger("setup.api");

export type SessionSummary = components["schemas"]["SessionSummary"];
export type SessionCreate = components["schemas"]["SessionCreate"];
export type LabInfo = components["schemas"]["LabInfo"];

/** List every session version on disk (open, closed and recovered); never primary data. */
export async function listSessions(fetchImpl: typeof fetch = fetch): Promise<Result<SessionSummary[], WizardFailure>> {
  const r = await getJson<SessionSummary[]>("/api/sessions", fetchImpl);
  return r.ok ? r : err(toFailure(r.error));
}

/** List the registered labs a new session can be started for. */
export async function listLabs(fetchImpl: typeof fetch = fetch): Promise<Result<LabInfo[], WizardFailure>> {
  const r = await getJson<LabInfo[]>("/api/labs", fetchImpl);
  return r.ok ? r : err(toFailure(r.error));
}

/** POST a JSON body and return the response; transport and http errors become a WizardFailure. */
async function postJson(path: string, body: unknown, fetchImpl: typeof fetch): Promise<Result<unknown, WizardFailure>> {
  log.info("write", { path });
  let res: Response;
  try {
    res = await fetchImpl(path, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    log.error("network failure", { path, message });
    return err({ kind: "transport", error: { kind: "network", message } });
  }
  if (!res.ok) {
    log.warn("write refused", { path, status: res.status });
    return err(toFailure({ kind: "http", status: res.status, body: await res.text() }));
  }
  return ok(await res.json());
}

/** Start a brand-new session family; the server allocates a fresh version, never reusing an id. */
export async function createSession(body: SessionCreate, fetchImpl: typeof fetch = fetch): Promise<Result<unknown, WizardFailure>> {
  return postJson("/api/sessions", body, fetchImpl);
}

/** Resume an existing session version as a new version (the original is left untouched). */
export async function resumeSession(name: string, fetchImpl: typeof fetch = fetch): Promise<Result<unknown, WizardFailure>> {
  return postJson("/api/sessions/resume", { name }, fetchImpl);
}

/** Human text for a failed session call. */
export function failureText(f: WizardFailure): string {
  if (f.kind === "problem") return `${f.problem.title}: ${f.problem.hint}`;
  return f.error.kind === "http" ? `Server error ${String(f.error.status)}` : `Network error: ${f.error.message}`;
}
