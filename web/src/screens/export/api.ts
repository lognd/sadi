// frob:ticket 01M6W7RATGKGPEYSMC5H8WGMBV
// frob:accept COV001 because="covered by ExportScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { getJson, type ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import { err, ok, type Result } from "../../api/result";
import { currentlySynthetic, exportFilename } from "../../state/provenance";
import type { ExportFormatView, Problem, ResultSet } from "./types";

const log = getLogger("screens.export.api");

/** URL that downloads (or returns inline) one export format. */
export function exportUrl(formatId: string): string {
  return `/api/export/${encodeURIComponent(formatId)}`;
}

/** Fetch the report (GET /api/results). */
export function getResults(fetchImpl: typeof fetch = fetch): Promise<Result<ResultSet, ApiError>> {
  return getJson<ResultSet>("/api/results", fetchImpl);
}

/** Fetch the lab's export formats (GET /api/export); an empty list is valid. */
export function getExportFormats(fetchImpl: typeof fetch = fetch): Promise<Result<ExportFormatView[], ApiError>> {
  return getJson<ExportFormatView[]>("/api/export", fetchImpl);
}

/** Fetch an inline JSON format (figure data) from GET /api/export/{id}. */
export function getFigureData(formatId: string, fetchImpl: typeof fetch = fetch): Promise<Result<unknown, ApiError>> {
  return getJson<unknown>(exportUrl(formatId), fetchImpl);
}

/** Best-effort open session name for file names; "" when there is none or the call fails. */
export async function getSessionName(fetchImpl: typeof fetch = fetch): Promise<string> {
  const r = await getJson<{ name?: unknown }>("/api/session", fetchImpl);
  if (!r.ok) {
    log.warn("session name unavailable", { kind: r.error.kind });
    return "";
  }
  return typeof r.value.name === "string" ? r.value.name : "";
}

/** Keep a rendered figure in the session folder (POST /api/export/figure/{id}); true when the server saved it. */
export async function keepFigure(figureId: string, blob: Blob, fetchImpl: typeof fetch = fetch): Promise<boolean> {
  try {
    const res = await fetchImpl(`/api/export/figure/${encodeURIComponent(figureId)}`, { method: "POST", body: blob });
    if (!res.ok) log.warn("figure copy not kept", { figureId, status: res.status });
    return res.ok;
  } catch (e) {
    log.warn("figure copy upload failed", { figureId, error: String(e) });
    return false;
  }
}

/** Turn an ApiError into a Problem, reading problem+json fields when the body has them. */
export function toProblem(e: ApiError): Problem {
  if (e.kind === "network") {
    return { title: "Network error", detail: e.message, hint: "Check that the SADI server is running.", status: null };
  }
  try {
    const j = JSON.parse(e.body) as Record<string, unknown>;
    const s = (k: string): string => (typeof j[k] === "string" ? j[k] : "");
    return { title: s("title") || `HTTP ${String(e.status)}`, detail: s("detail"), hint: s("hint"), status: e.status };
  } catch {
    log.warn("non-json error body", { status: e.status });
    return { title: `HTTP ${String(e.status)}`, detail: e.body, hint: "", status: e.status };
  }
}

/** A downloaded export: bytes, file name and where the server kept its own copy ("" when none, "failed" when it could not). */
export interface DownloadedExport {
  readonly blob: Blob;
  readonly filename: string;
  readonly saved: string;
}

/** Name from a Content-Disposition header, else `fallback`. */
export function dispositionName(header: string | null, fallback: string): string {
  const m = header === null ? null : /filename="?([^";]+)"?/.exec(header);
  return m?.[1] ?? fallback;
}

/** Download one export format with fetch so a refusal can be shown in the page; never throws. */
export function downloadExport(formatId: string, fetchImpl: typeof fetch = fetch): Promise<Result<DownloadedExport, ApiError>> {
  return downloadFrom(exportUrl(formatId), formatId, fetchImpl);
}

/** Fetch `url` as an export download (any non-2xx becomes an ApiError carrying the problem body); never throws. */
export async function downloadFrom(url: string, formatId: string, fetchImpl: typeof fetch = fetch): Promise<Result<DownloadedExport, ApiError>> {
  log.info("download requested", { formatId, url });
  let res: Response;
  try {
    res = await fetchImpl(url);
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    log.error("download network failure", { formatId, message });
    return err({ kind: "network", message });
  }
  if (!res.ok) {
    const body = await res.text();
    log.warn("download refused", { formatId, status: res.status });
    return err({ kind: "http", status: res.status, body });
  }
  const blob = await res.blob();
  const name = dispositionName(res.headers.get("Content-Disposition"), `sadi-${formatId}.csv`);
  const saved = res.headers.get("X-SADI-Saved") ?? "";
  log.info("download fetched", { formatId, bytes: blob.size, saved });
  // frob:ticket 01M72D3CTDED2MGDY721RSM8M4
  // The server stamps provenance and names the file (incl. RECOVERED-); trust it as is.
  const prov = res.headers.get("X-SADI-Provenance");
  const filename = prov !== null ? name : exportFilename(name, currentlySynthetic());
  return ok({ blob, filename, saved });
}

/** Page message for the server's saved-copy header, or "" when it sent none. */
export function savedMessage(saved: string): string {
  if (saved === "") return "";
  if (saved === "failed") return "Downloaded, but SADI could not keep its own copy in the session folder.";
  return `Saved a copy in ${saved}`;
}
