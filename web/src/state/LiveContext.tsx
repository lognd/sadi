// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:accept COV001 because="covered by LiveContext.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { createContext, useContext } from "react";
import { getLogger } from "../api/log";
import type { UseTraceOptions } from "../hooks/useTrace";
import { useRunLive, type RunLive } from "../screens/run/useRunLive";

const log = getLogger("state.live");

/** Context holding the single app-wide stream subscription; null outside a provider. */
export const LiveContext = createContext<RunLive | null>(null);

/** Props of the provider. */
export interface LiveProviderProps {
  readonly children?: React.ReactNode;
  /** Force the Source word to Simulated (otherwise the server hello decides). */
  readonly simulated?: boolean;
  /** Trace options; `open` is injectable for tests. */
  readonly trace?: UseTraceOptions;
}

/** Opens the one /api/stream subscription for the whole app and shares it with every step. */
export function LiveProvider({ children, simulated, trace }: LiveProviderProps): React.JSX.Element {
  const live = useRunLive({ ...trace, ...(simulated === undefined ? {} : { simulated }) });
  return <LiveContext.Provider value={live}>{children}</LiveContext.Provider>;
}

/** The shared live feed; a missing provider is a programmer bug. */
export function useLive(): RunLive {
  const live = useContext(LiveContext);
  if (live === null) {
    log.error("useLive called outside LiveProvider");
    throw new Error("useLive must be used inside <LiveProvider>");
  }
  return live;
}
