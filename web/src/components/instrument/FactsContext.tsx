// frob:ticket 01M727VHZTQHYABYCT6XTASEM1
import { createContext, useContext } from "react";
import type { BackendFacts } from "./useBackendFacts";

/** Empty facts: nothing known, so the save indicator reads "No session". */
export const NO_FACTS: BackendFacts = { save: null, device: null, session: null, rootLockOk: null, dataRoot: null, version: null, lastError: null };

/** Carries the one polled BackendFacts down to the status bar so every indicator shares a source. */
export const FactsContext = createContext<BackendFacts>(NO_FACTS);

/** Forces an immediate poll of every status endpoint (including /api/session); a no-op outside a provider. */
export const RefreshFactsContext = createContext<() => void>(() => undefined);

/** Get the function that refreshes the shared facts now (call after opening or closing a session). */
export function useRefreshFacts(): () => void { return useContext(RefreshFactsContext); }

/** Read the shared backend facts (NO_FACTS outside a provider). */
export function useFacts(): BackendFacts { return useContext(FactsContext); }
