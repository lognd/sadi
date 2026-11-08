import { create } from "zustand";
import { getLogger } from "../api/log";

const log = getLogger("doctor.route");

/** Whether the doctor screen is showing; any wizard step or error handler can open it. */
export interface DoctorRouteState {
  visible: boolean;
  open: (reason: string) => void;
  close: () => void;
}

/** Store hook for doctor visibility. */
export const useDoctorRoute = create<DoctorRouteState>()((set) => ({
  visible: false,
  open: (reason) => {
    log.info("doctor opened", { reason });
    set({ visible: true });
  },
  close: () => {
    log.info("doctor closed");
    set({ visible: false });
  },
}));

/** Hook for connection-error UI: returns a callback that opens the doctor. */
export function openDoctorOnConnectionError(): void {
  useDoctorRoute.getState().open("connection-error");
}
