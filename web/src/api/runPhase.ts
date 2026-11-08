// frob:ticket 01M6XAZ42NR9WARFYVZMS85NR2
import { getLogger } from "./log";
import { err, ok, type Result } from "./result";
import type { components } from "./schema";
import { toFailure, type WizardFailure } from "../components/wizard/wizardApi";

const log = getLogger("api.runPhase");

export type RunPhaseView = components["schemas"]["RunPhaseView"];
export type ServerPhase = components["schemas"]["RunPhaseBody"]["phase"];

/** Endpoint holding the server-recorded guided-run phase. */
export const RUN_PHASE_PATH = "/api/session/run-phase";

/** Guided-run phases the server knows, in the only order it accepts. */
export const SERVER_PHASES: readonly ServerPhase[] = ["calibrate", "elastic", "plastic"];

/** True when a wizard screen kind is a phase the server tracks (tare is not). */
export function isServerPhase(s: string): s is ServerPhase {
  return (SERVER_PHASES as readonly string[]).includes(s);
}

async function call(init: RequestInit, fetchImpl: typeof fetch): Promise<Result<RunPhaseView, WizardFailure>> {
  let res: Response;
  try {
    res = await fetchImpl(RUN_PHASE_PATH, init);
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    log.error("network failure", { method: init.method, message });
    return err({ kind: "transport", error: { kind: "network", message } });
  }
  if (!res.ok) {
    log.warn("run-phase refused", { method: init.method, status: res.status });
    return err(toFailure({ kind: "http", status: res.status, body: await res.text() }));
  }
  return ok((await res.json()) as RunPhaseView);
}

/** Fetch the recorded run phase (GET /api/session/run-phase). */
export function getRunPhase(fetchImpl: typeof fetch = fetch): Promise<Result<RunPhaseView, WizardFailure>> {
  return call({ headers: { Accept: "application/json" } }, fetchImpl);
}

/** Enter a run phase (POST /api/session/run-phase); only the next phase is legal, else 409 with a hint. */
export function postRunPhase(phase: ServerPhase, fetchImpl: typeof fetch = fetch): Promise<Result<RunPhaseView, WizardFailure>> {
  log.info("enter phase", { phase });
  return call(
    { method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" }, body: JSON.stringify({ phase }) },
    fetchImpl,
  );
}

/**
 * Tell the server the wizard is in `target`: no-op when already there or past it, otherwise
 * POST each missing phase in order (so a resumed session catches up). A refusal is returned as-is.
 */
export async function enterRunPhase(target: ServerPhase, fetchImpl: typeof fetch = fetch): Promise<Result<RunPhaseView, WizardFailure>> {
  const cur = await getRunPhase(fetchImpl);
  if (!cur.ok) return cur;
  let view = cur.value;
  const want = SERVER_PHASES.indexOf(target);
  for (let i = 0; i <= SERVER_PHASES.length; i++) {
    const at = view.phase === null ? -1 : SERVER_PHASES.indexOf(view.phase);
    if (at >= want) {
      log.debug("already in or past phase", { target, recorded: view.phase });
      return ok(view);
    }
    const next = SERVER_PHASES[at + 1];
    if (next === undefined) return ok(view);
    const r = await postRunPhase(next, fetchImpl);
    if (!r.ok) return r;
    view = r.value;
  }
  return ok(view);
}
