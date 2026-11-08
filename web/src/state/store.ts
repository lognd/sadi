import { create } from "zustand";
import { getLogger } from "../api/log";

const log = getLogger("state.store");

/** Connection slice: backend reachability. */
export interface ConnectionSlice {
  connection: "unknown" | "up" | "down";
  setConnection: (next: ConnectionSlice["connection"]) => void;
}

/** Session slice: id of the active session, if any. */
export interface SessionSlice {
  sessionId: string | null;
  setSessionId: (id: string | null) => void;
}

/** Whole application state: later tickets add slices here. */
export type AppState = ConnectionSlice & SessionSlice;

/** Global typed store hook. */
export const useStore = create<AppState>()((set) => ({
  connection: "unknown",
  setConnection: (next) => {
    log.info("connection changed", { next });
    set({ connection: next });
  },
  sessionId: null,
  setSessionId: (id) => {
    log.info("session changed", { id });
    set({ sessionId: id });
  },
}));
