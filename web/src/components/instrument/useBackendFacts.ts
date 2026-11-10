// frob:ticket 01M7274EH583A30335TGGT6ZZ1
// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
// frob:ticket 01M729FVNSJCVAHK4XBSG9NBYC
/** Polls the light status endpoints that feed the debug strip. */
import { useCallback, useEffect, useRef, useState } from "react";
import { getDoctor, getJson } from "../../api/client";
import { getLogger } from "../../api/log";

const log = getLogger("instrument.facts");

/** Poll period for the status endpoints in ms. */
export const FACTS_POLL_MS = 2000;

/** While no session is open, /api/session is polled only every Nth tick (audit #37). */
export const NO_SESSION_POLL_EVERY = 5;

/** Everything the debug strip reads from REST; null means "not known yet or unavailable". */
export interface BackendFacts {
  readonly save: { readonly state: string; readonly label: string; readonly pending: number; readonly hint: string } | null;
  readonly device: { readonly status: string; readonly attached: boolean; readonly fault: string | null; readonly hint: string; readonly stopReason: string | null; readonly acquisitionFault: string | null } | null;
  readonly session: { readonly name: string; readonly lab: string; readonly durableSeq: number | null } | null;
  readonly rootLockOk: boolean | null;
  readonly dataRoot: string | null;
  readonly version: string | null;
  readonly lastError: string | null;
}

const EMPTY: BackendFacts = { save: null, device: null, session: null, rootLockOk: null, dataRoot: null, version: null, lastError: null };

interface SaveWire { state?: string; label?: string; pending?: number; hint?: string }
interface DeviceWire { status?: string; attached?: boolean; fault?: string | null; hint?: string; stop_reason?: string | null; acquisition_fault?: string | null }

/** Operator text for why raw streaming stopped or faulted (empty when running normally). */
function acquisitionHint(d: DeviceWire): string {
  if (d.acquisition_fault) return `Acquisition fault: ${d.acquisition_fault}`;
  return d.stop_reason ? `Raw streaming stopped (${d.stop_reason}); recorded data is safe.` : "";
}
interface SessionWire { name?: string; lab?: string; durable_seq?: number | null }
interface LockWire { ok?: boolean; hint?: string }

/** Fetch every status endpoint once and fold the answers into one BackendFacts (never throws); pollSession=false keeps prev.session and skips /api/session. */
export async function fetchFacts(prev: BackendFacts, fetchImpl: typeof fetch = fetch, pollSession = true): Promise<BackendFacts> {
  const [save, dev, ses, lock] = await Promise.all([
    getJson<SaveWire>("/api/save-indicator", fetchImpl),
    getJson<DeviceWire>("/api/device/status", fetchImpl),
    pollSession ? getJson<SessionWire>("/api/session", fetchImpl) : Promise.resolve(null),
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
    device: d === null ? null : { status: d.status ?? "unknown", attached: d.attached ?? false, fault: d.fault ?? null, hint: d.hint || acquisitionHint(d), stopReason: d.stop_reason ?? null, acquisitionFault: d.acquisition_fault ?? null },
    session: ses === null ? prev.session : ses.ok ? { name: ses.value.name ?? "", lab: ses.value.lab ?? "", durableSeq: ses.value.durable_seq ?? null } : null,
    rootLockOk: lock.ok ? lock.value.ok !== false : null,
    lastError: errs.length > 0 ? errs.join("; ") : null,
  };
}

/** Poll the status endpoints (refresh() polls everything now, e.g. right after a session opens or closes); read host facts (data folder, version) from the doctor, retrying until known (audit #10). */
export function useBackendFacts(fetchImpl: typeof fetch = fetch): { readonly facts: BackendFacts; readonly refresh: () => void } {
  const [facts, setFacts] = useState<BackendFacts>(EMPTY);
  const latest = useRef<BackendFacts>(EMPTY);
  const forceTick = useRef<() => void>(() => undefined);
  const refresh = useCallback((): void => { forceTick.current(); }, []);
  useEffect(() => {
    let live = true;
    let n = 0;
    let hostBusy = false;
    const apply = (f: (p: BackendFacts) => BackendFacts): void => {
      if (!live) return;
      latest.current = f(latest.current);
      setFacts(latest.current);
    };
    const loadHost = (): void => {
      if (hostBusy || latest.current.dataRoot !== null) return;
      hostBusy = true;
      void getDoctor(fetchImpl).then((r) => {
        hostBusy = false;
        if (!r.ok) { log.warn("doctor host facts unavailable; will retry"); return; }
        const host = (r.value as unknown as { host?: { data_root?: string; sadi_version?: string } }).host;
        apply((p) => ({ ...p, dataRoot: host?.data_root ?? null, version: host?.sadi_version ?? null }));
      });
    };
    const tick = (force = false): void => {
      const pollSession = force || latest.current.session !== null || n % NO_SESSION_POLL_EVERY === 0;
      n += 1;
      void fetchFacts(latest.current, fetchImpl, pollSession).then((f) => { apply((p) => ({ ...f, dataRoot: p.dataRoot, version: p.version })); });
      loadHost();
    };
    forceTick.current = () => { log.info("facts refresh requested"); tick(true); };
    tick();
    const id = setInterval(() => { tick(); }, FACTS_POLL_MS);
    return () => { live = false; forceTick.current = () => undefined; clearInterval(id); };
  }, [fetchImpl]);
  return { facts, refresh };
}
