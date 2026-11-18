// frob:ticket 01M6X1GGD923K25M13JM84ZB2J
/** POST /api/session/load-change: durably mark that a load was applied so the settle detector opens a new point. */
import { getLogger } from "../../api/log";
import type { Result } from "../../api/result";
import { postJson, type PostError } from "../review/api";

const log = getLogger("screens.run.loadChange");

/** Response of the load-change route: WAL seq of the recorded marker. */
export interface LoadChangeOut {
  readonly marker_seq: number;
}

/** Mark a load change on the live run; the error carries the server's 409 body when no run is live. */
export async function postLoadChange(f: typeof fetch = fetch): Promise<Result<LoadChangeOut, PostError>> {
  const r = await postJson<LoadChangeOut>("/api/session/load-change", {}, f);
  if (r.ok) log.info("load change marked", { seq: r.value.marker_seq });
  else log.warn("load change refused", { kind: r.error.kind });
  return r;
}
