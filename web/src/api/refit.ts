// frob:ticket 01M6WMGMJE0WEXXNQ3AD754A8M
import { getLogger } from "./log";
import { err, ok, type Result } from "./result";
import type { ApiError } from "./client";
import type { FitWindow, ModulusFitView } from "../plots/stressstrain/model";

const log = getLogger("api.refit");

/** Endpoint the backend must expose to refit E over a window (server side filed as a follow-up ticket). */
export const REFIT_PATH = "/api/stress-strain/fit";

/** POST a fit window to the refit endpoint and return the new modulus fit, never throwing. */
export async function refitModulus(
  window: FitWindow,
  fetchImpl: typeof fetch = fetch,
): Promise<Result<ModulusFitView, ApiError>> {
  log.debug("request", { path: REFIT_PATH, window });
  let res: Response;
  try {
    res = await fetchImpl(REFIT_PATH, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ first: window.first, last: window.last }),
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    log.error("network failure", { path: REFIT_PATH, message });
    return err({ kind: "network", message });
  }
  if (!res.ok) {
    log.warn("http error", { path: REFIT_PATH, status: res.status });
    return err({ kind: "http", status: res.status, body: await res.text() });
  }
  return ok((await res.json()) as ModulusFitView);
}
