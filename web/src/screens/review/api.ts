// frob:ticket 01M6W7RARKCF5E5N60RFHNEDX8
// frob:accept COV001 because="covered by ReviewScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { getJson, type ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import { err, ok, type Result } from "../../api/result";
import type { ResultSet } from "../../components/results/types";
import type { Committed, EditRequest, HistoryState, PointView, Problem } from "./types";

const log = getLogger("screens.review.api");

/** POST JSON (or nothing) and return the parsed body or an ApiError Result. */
export async function postJson<T>(
  path: string,
  body: unknown,
  fetchImpl: typeof fetch = fetch,
): Promise<Result<T, ApiError>> {
  log.debug("request", { path, method: "POST" });
  let res: Response;
  try {
    res = await fetchImpl(path, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    log.error("network failure", { path, message });
    return err({ kind: "network", message });
  }
  if (!res.ok) {
    log.warn("http error", { path, status: res.status });
    return err({ kind: "http", status: res.status, body: await res.text() });
  }
  return ok((await res.json()) as T);
}

/** List captured points (GET /api/session/points). */
export const getPoints = (f?: typeof fetch): Promise<Result<PointView[], ApiError>> =>
  getJson<PointView[]>("/api/session/points", f);

/** Undo and redo stacks (GET /api/session/history). */
export const getHistory = (f?: typeof fetch): Promise<Result<HistoryState, ApiError>> =>
  getJson<HistoryState>("/api/session/history", f);

/** Raw recompute of all results (GET /api/results). */
export const getResults = (f?: typeof fetch): Promise<Result<ResultSet, ApiError>> =>
  getJson<ResultSet>("/api/results", f);

/** Append an edit of one point as a compensating record (POST /api/session/points/{id}/edit). */
export const editPoint = (id: string, req: EditRequest, f?: typeof fetch): Promise<Result<Committed, ApiError>> =>
  postJson<Committed>(`/api/session/points/${encodeURIComponent(id)}/edit`, req, f);

/** Undo the latest action as a compensating edit (POST /api/session/undo). */
export const undo = (f?: typeof fetch): Promise<Result<Committed, ApiError>> =>
  postJson<Committed>("/api/session/undo", undefined, f);

/** Redo the latest undone action (POST /api/session/redo). */
export const redo = (f?: typeof fetch): Promise<Result<Committed, ApiError>> =>
  postJson<Committed>("/api/session/redo", undefined, f);

/** Message for an API failure: the problem+json title, detail and hint when parseable, else the raw status. */
export function describeProblem(e: ApiError): string {
  if (e.kind === "network") return `Network error: ${e.message}. Check the connection and try again.`;
  try {
    const p = JSON.parse(e.body) as Partial<Problem>;
    if (typeof p.title === "string") {
      const detail = p.detail ? `: ${p.detail}` : "";
      const hint = p.hint ? ` Hint: ${p.hint}` : "";
      return `${p.title}${detail}.${hint}`.replace("..", ".");
    }
  } catch {
    // not JSON; fall through to the raw form
  }
  return `Request failed (HTTP ${String(e.status)}): ${e.body}`;
}
