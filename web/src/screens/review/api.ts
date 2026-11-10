// frob:ticket 01M6W7RARKCF5E5N60RFHNEDX8
// frob:accept COV001 because="covered by ReviewScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { plainNote } from "../../components/wizard/plainText";
import { getJson, type ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import { err, ok, type Result } from "../../api/result";
import type { ResultSet } from "../../components/results/types";
import type { Committed, EditRequest, HistoryState, PointView, Problem } from "./types";

const log = getLogger("screens.review.api");

/** The parts of a problem+json body a student may read, parsed once. */
export interface ProblemParts {
  readonly type: string;
  readonly title: string;
  readonly detail: string;
  readonly hint: string;
}

/** An ApiError whose http form also carries the parsed problem (null when the body was not problem JSON). */
export type PostError =
  | { kind: "network"; message: string }
  | { kind: "http"; status: number; body: string; problem: ProblemParts | null };

/** Parse a problem+json body once; null when it is not one. */
function parseProblem(body: string): ProblemParts | null {
  try {
    const p = JSON.parse(body) as Partial<Problem> | null;
    if (p === null || typeof p !== "object" || typeof p.title !== "string") return null;
    return { type: p.type ?? "", title: p.title, detail: p.detail ?? "", hint: p.hint ?? "" };
  } catch {
    return null;
  }
}

/** A 5xx on capture may have saved the point, so the wording says so and tells the student to retry safely. */
const UNCERTAIN_CAPTURE = "Capture not confirmed yet. Press Accept again to check; it will not be saved twice.";

/** Plain-text message for a failed POST: hint, else detail, else title; never raw JSON or an HTTP code (status stays in the log). */
export function problemText(e: PostError, what: string): string {
  if (e.kind === "network") return `Network error: ${e.message}. Check the connection, then try again.`;
  // frob:ticket 01M72YKEWHJJXEBBV7XDP5Z31J
  if (e.status >= 500 && what === "Capture") return UNCERTAIN_CAPTURE;
  const p = e.problem;
  const text = p === null ? "" : p.hint !== "" ? p.hint : p.detail !== "" ? p.detail : p.title;
  return text === "" ? `${what} was refused. Try again.` : `${what} refused. ${plainNote(text)}`;
}

/** True when the failure is the server saying this request id was already used for a different point. */
export function isRequestIdReused(e: PostError): boolean {
  return e.kind === "http" && e.problem !== null && e.problem.type.endsWith("request_id_reused");
}

/** POST JSON (or nothing) and return the parsed body or a PostError Result. */
export async function postJson<T>(
  path: string,
  body: unknown,
  fetchImpl: typeof fetch = fetch,
): Promise<Result<T, PostError>> {
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
    const body = await res.text();
    const problem = parseProblem(body);
    log.warn("http error", { path, status: res.status, type: problem?.type ?? null });
    return err({ kind: "http", status: res.status, body, problem });
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
      const detail = p.detail ? `: ${plainNote(p.detail)}` : "";
      const hint = p.hint ? ` Hint: ${p.hint}` : "";
      return `${p.title}${detail}.${hint}`.replace("..", ".");
    }
  } catch {
    // not JSON; fall through to the raw form
  }
  return `Request failed (HTTP ${String(e.status)}): ${e.body}`;
}
