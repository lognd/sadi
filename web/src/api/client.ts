import { getLogger } from "./log";
import { err, ok, type Result } from "./result";
import type { components } from "./schema";

const log = getLogger("api.client");

/** Failure modes of an API call. */
export type ApiError =
  | { kind: "network"; message: string }
  | { kind: "http"; status: number; body: string };

/** Health payload as declared by the OpenAPI schema. */
export type Health = components["schemas"]["Health"];

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
