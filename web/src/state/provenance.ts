// frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
// frob:ticket 01M71VN3JDC5NDPJ2AW60KQX63
/** Data-provenance state: the single source of truth for "is the data on screen synthetic?". */
import { useEffect } from "react";
import { create } from "zustand";
import { getHealth } from "../api/client";
import { getLogger } from "../api/log";
import type { components } from "../api/schema";

const log = getLogger("state.provenance");

/** Provenance stamp carried on backend payloads (generated schema type). */
export type DataProvenance = components["schemas"]["DataProvenance"];

/** Banner text; mirrors python/sadi/synthetic/provenance.py SYNTHETIC_LABEL. */
export const SYNTHETIC_LABEL = "SYNTHETIC DATA - NOT A MEASUREMENT";
/** Filename prefix on every synthetic export; mirrors EXPORT_PREFIX in the backend. */
export const EXPORT_PREFIX = "SYNTHETIC-";
/** How often the health endpoint is re-read for provenance, in ms. */
export const PROVENANCE_POLL_MS = 5000;

/** True only when a stamp explicitly says synthetic; absent or real stamps are never synthetic. */
export function isSynthetic(p: DataProvenance | null | undefined): boolean {
  return p !== null && p !== undefined && (p.synthetic || p.source === "synthetic");
}

/** Prefix a download filename with SYNTHETIC- when the data is synthetic (idempotent). */
export function exportFilename(name: string, synthetic: boolean): string {
  // frob:ticket 01M72D3CTDED2MGDY721RSM8M4
  return synthetic && !name.includes(EXPORT_PREFIX) ? `${EXPORT_PREFIX}${name}` : name;
}

/** Store slice holding the latest provenance seen on any payload. */
export interface ProvenanceState {
  provenance: DataProvenance | null;
  observe: (p: DataProvenance | null | undefined) => void;
}

/** Global provenance store; `observe` feeds it from any payload that carries a stamp. */
export const useProvenance = create<ProvenanceState>()((set, get) => ({
  provenance: null,
  observe: (p) => {
    if (p === null || p === undefined) return;
    if (isSynthetic(p) !== isSynthetic(get().provenance)) log.warn("provenance changed", { source: p.source });
    set({ provenance: p });
  },
}));

/** Non-hook read for event handlers: is the data currently synthetic? */
export function currentlySynthetic(): boolean {
  return isSynthetic(useProvenance.getState().provenance);
}

/** Poll /api/health and feed its provenance into the store; mount once at the app root. */
export function useProvenancePoll(fetchImpl: typeof fetch = fetch): void {
  const observe = useProvenance((s) => s.observe);
  useEffect(() => {
    let live = true;
    const tick = (): void => {
      void getHealth(fetchImpl).then((r) => { if (live && r.ok) observe(r.value.provenance); });
    };
    tick();
    const id = setInterval(tick, PROVENANCE_POLL_MS);
    return () => { live = false; clearInterval(id); };
  }, [fetchImpl, observe]);
}
