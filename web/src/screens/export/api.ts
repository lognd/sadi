// frob:ticket 01M6W7RATGKGPEYSMC5H8WGMBV
import { getJson, type ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import type { Result } from "../../api/result";
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
