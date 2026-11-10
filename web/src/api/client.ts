// frob:ticket 01M7274EH583A30335TGGT6ZZ1
import { getLogger } from "./log";
import { err, ok, type Result } from "./result";
import type { components } from "./schema";
import type { CheckResult, DoctorReport } from "../doctor/types";

const log = getLogger("api.client");

/** Failure modes of an API call. */
export type ApiError =
  | { kind: "network"; message: string }
  | { kind: "http"; status: number; body: string };

/** Health payload; the backend publishes no /api/health route yet, so this is hand-declared. */
export interface Health {
  status: string;
  version: string;
  /** Data provenance stamp; absent on older backends (treated as real). */
  provenance?: components["schemas"]["DataProvenance"];
}

/** Fetch JSON from an API path, returning a Result instead of throwing. */
export async function getJson<T>(
  path: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Result<T, ApiError>> {
  log.debug("request", { path });
  let res: Response;
  try {
    res = await fetchImpl(path, { headers: { Accept: "application/json" } });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    log.error("network failure", { path, message });
    return err({ kind: "network", message });
  }
  if (!res.ok) {
    const body = await res.text();
    log.warn("http error", { path, status: res.status });
    return err({ kind: "http", status: res.status, body });
  }
  log.debug("response ok", { path, status: res.status });
  return ok((await res.json()) as T);
}

/** Query the backend health endpoint. */
export function getHealth(fetchImpl: typeof fetch = fetch): Promise<Result<Health, ApiError>> {
  return getJson<Health>("/api/health", fetchImpl);
}

/** Fetch the full doctor report (GET /api/doctor). */
export function getDoctor(fetchImpl: typeof fetch = fetch): Promise<Result<DoctorReport, ApiError>> {
  return getJson<DoctorReport>("/api/doctor", fetchImpl);
}

/** Re-run one doctor check (POST /api/doctor/{id}/run) and return its fresh result. */
export async function runDoctorCheck(
  checkId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Result<CheckResult, ApiError>> {
  const path = `/api/doctor/${encodeURIComponent(checkId)}/run`;
  log.debug("request", { path, method: "POST" });
  let res: Response;
  try {
    res = await fetchImpl(path, { method: "POST", headers: { Accept: "application/json" } });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    log.error("network failure", { path, message });
    return err({ kind: "network", message });
  }
  if (!res.ok) {
    log.warn("http error", { path, status: res.status });
    return err({ kind: "http", status: res.status, body: await res.text() });
  }
  return ok((await res.json()) as CheckResult);
}

/** Reconnect outcome: the refreshed device view from POST /api/device/reconnect. */
export type ReconnectView = components["schemas"]["DeviceView"];

/** Ask the backend to open the board now (POST /api/device/reconnect); the open session and its WAL are untouched. */
export async function postReconnect(fetchImpl: typeof fetch = fetch): Promise<Result<ReconnectView, ApiError>> {
  const path = "/api/device/reconnect";
  log.info("reconnect requested", { path });
  let res: Response;
  try {
    res = await fetchImpl(path, { method: "POST", headers: { Accept: "application/json" } });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    log.error("network failure", { path, message });
    return err({ kind: "network", message });
  }
  if (!res.ok) {
    log.warn("http error", { path, status: res.status });
    return err({ kind: "http", status: res.status, body: await res.text() });
  }
  return ok((await res.json()) as ReconnectView);
}
