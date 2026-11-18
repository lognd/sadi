// frob:ticket 01M72ZDQGAN0VQRKHM489H28J1
// frob:accept COV001 because="covered by ExportNow.test.tsx (vitest); TypeScript frob:tests does not resolve and grimble is not installed here"
import { useCallback, useState } from "react";
import { getLogger } from "../../api/log";
import { downloadExport, savedMessage, toProblem } from "../../screens/export/api";
import { saveBlob } from "../../screens/export/ExportScreen";

const log = getLogger("wizard.export_now");

/** Mid-run export formats offered on every step (ids match the lctt lab's export formats). */
export const EXPORT_NOW_FORMATS: readonly { readonly id: string; readonly label: string }[] = [
  { id: "lctt-csv-partial", label: "Export now (partial CSV)" },
  { id: "lctt-calibration-csv", label: "Export calibration CSV" },
];

/** Download one mid-run export and hand it to `save`; returns the message to show (never throws, never stops the run). */
export async function exportNow(
  formatId: string,
  save: (blob: Blob, name: string) => void = saveBlob,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const r = await downloadExport(formatId, fetchImpl);
  if (!r.ok) {
    const p = toProblem(r.error);
    log.warn("export now refused", { formatId, title: p.title });
    return `${p.title}${p.detail === "" ? "" : ` - ${p.detail}`}${p.hint === "" ? "" : ` ${p.hint}`}`;
  }
  save(r.value.blob, r.value.filename);
  log.info("export now saved", { formatId, name: r.value.filename });
  return savedMessage(r.value.saved) || `Downloaded ${r.value.filename}`;
}

/** Shell buttons that export what is captured so far from any step; each file is labelled PARTIAL and a new copy, so nothing is overwritten. */
export function ExportNow(): React.JSX.Element {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const go = useCallback((id: string): void => {
    setBusy(true);
    void exportNow(id).then((m) => { setMessage(m); setBusy(false); });
  }, []);
  return (
    <div className="export-now" aria-label="Export now">
      {EXPORT_NOW_FORMATS.map((f) => (
        <button key={f.id} type="button" disabled={busy} onClick={() => { go(f.id); }}>{f.label}</button>
      ))}
      {message === "" ? null : <span role="status" className="export-now-msg">{message}</span>}
    </div>
  );
}
