// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
/** Polls the light status endpoints that feed the debug strip. */
import { useEffect, useState } from "react";
import { getDoctor, getJson } from "../../api/client";
import { getLogger } from "../../api/log";

const log = getLogger("instrument.facts");

/** Poll period for the status endpoints in ms. */
export const FACTS_POLL_MS = 2000;

/** Everything the debug strip reads from REST; null means "not known yet or unavailable". */
export interface BackendFacts {
  readonly save: { readonly state: string; readonly label: string; readonly pending: number; readonly hint: string } | null;
  readonly device: { readonly status: string; readonly attached: boolean; readonly fault: string | null; readonly hint: string } | null;
  readonly session: { readonly name: string; readonly lab: string; readonly durableSeq: number | null } | null;
  readonly rootLockOk: boolean | null;
  readonly dataRoot: string | null;
  readonly version: string | null;
  readonly lastError: string | null;
}

const EMPTY: BackendFacts = { save: null, device: null, session: null, rootLockOk: null, dataRoot: null, version: null, lastError: null };

interface SaveWire { state?: string; label?: string; pending?: number; hint?: string }
interface DeviceWire { status?: string; attached?: boolean; fault?: string | null; hint?: string }
interface SessionWire { name?: string; lab?: string; durable_seq?: number | null }
interface LockWire { ok?: boolean; hint?: string }

/** Fetch every status endpoint once and fold the answers into one BackendFacts (never throws). */
export async function fetchFacts(prev: BackendFacts, fetchImpl: typeof fetch = fetch): Promise<BackendFacts> {
  const [save, dev, ses, lock] = await Promise.all([
    getJson<SaveWire>("/api/save-indicator", fetchImpl),
    getJson<DeviceWire>("/api/device/status", fetchImpl),
    getJson<SessionWire>("/api/session", fetchImpl),
    getJson<LockWire>("/api/root-lock", fetchImpl),
  ]);
  const errs: string[] = [];
  if (!save.ok) errs.push("Save status unreachable");
  if (!dev.ok) errs.push("Device status unreachable");
  const d = dev.ok ? dev.value : null;
  if (d?.fault) errs.push(d.fault);
  if (lock.ok && lock.value.ok === false) errs.push(lock.value.hint ?? "Data folder is locked by another SADI");
  return {
    ...prev,
    save: save.ok ? { state: save.value.state ?? "unknown", label: save.value.label ?? "", pending: save.value.pending ?? 0, hint: save.value.hint ?? "" } : null,
    device: d === null ? null : { status: d.status ?? "unknown", attached: d.attached ?? false, fault: d.fault ?? null, hint: d.hint ?? "" },
    session: ses.ok ? { name: ses.value.name ?? "", lab: ses.value.lab ?? "", durableSeq: ses.value.durable_seq ?? null } : null,
    rootLockOk: lock.ok ? lock.value.ok !== false : null,
    lastError: errs.length > 0 ? errs.join("; ") : null,
  };
}

/** Poll the status endpoints and read host facts (data folder, version) from the doctor once. */
export function useBackendFacts(fetchImpl: typeof fetch = fetch): BackendFacts {
  const [facts, setFacts] = useState<BackendFacts>(EMPTY);
  useEffect(() => {
    let live = true;
    const tick = (): void => {
      void fetchFacts(EMPTY, fetchImpl).then((f) => { if (live) setFacts((p) => ({ ...f, dataRoot: p.dataRoot, version: p.version })); });
    };
    tick();
    const id = setInterval(tick, FACTS_POLL_MS);
    void getDoctor(fetchImpl).then((r) => {
      if (!live || !r.ok) { log.warn("doctor host facts unavailable"); return; }
      const host = (r.value as unknown as { host?: { data_root?: string; sadi_version?: string } }).host;
      setFacts((p) => ({ ...p, dataRoot: host?.data_root ?? null, version: host?.sadi_version ?? null }));
    });
    return () => { live = false; clearInterval(id); };
  }, [fetchImpl]);
  return facts;
}
