// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// frob:ticket 01M6WWN96C55R68VNZF2D1NB2V
// frob:ticket 01M727YGXCC6ZFVHWHG64KFA7D
import type { ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import { err, ok, type Result } from "../../api/result";
import { currentlySynthetic, exportFilename } from "../../state/provenance";
import { dispositionName, exportUrl } from "../export/api";

const log = getLogger("screens.run.export");

/** Export format the run screen's F3 requests unless the host overrides it. */
export const DEFAULT_RUN_EXPORT = "lctt-csv";

/** A downloaded export: the bytes and a suggested file name. */
export interface RunExport {
  readonly blob: Blob;
  readonly filename: string;
}

/** Fetch one export format from GET /api/export/{format}; failures come back as a Result, never thrown. */
export async function fetchRunExport(format: string, fetchImpl: typeof fetch = fetch): Promise<Result<RunExport, ApiError>> {
  const path = exportUrl(format);
  log.info("export requested", { format });
  let res: Response;
  try {
    res = await fetchImpl(path);
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    log.error("export network failure", { format, message });
    return err({ kind: "network", message });
  }
  if (!res.ok) {
    const body = await res.text();
    log.warn("export http error", { format, status: res.status });
    return err({ kind: "http", status: res.status, body });
  }
  const blob = await res.blob();
  log.info("export fetched", { format, bytes: blob.size });
  const name = dispositionName(res.headers.get("Content-Disposition"), `sadi-${format}.csv`);
  // The server's own synthetic stamp wins over the polled store, so a stale store cannot unlabel a file.
  const synthetic = currentlySynthetic() || (res.headers.get("X-Sadi-Provenance") ?? "").toLowerCase().includes("synthetic");
  return ok({ blob, filename: exportFilename(name, synthetic) });
}

/** User-facing text for a failed export. */
export function exportErrorText(e: ApiError): string {
  return e.kind === "network"
    ? `Export failed: ${e.message}. Check the connection, then press F3 again.`
    : `Export refused (HTTP ${String(e.status)}). ${e.body}`;
}
