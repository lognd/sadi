import { useEffect } from "react";
import { getHealth } from "./api/client";
import { getLogger } from "./api/log";
import { DoctorScreen } from "./doctor/DoctorScreen";
import { openDoctorOnConnectionError, useDoctorRoute } from "./doctor/useDoctorRoute";
import { WizardHost } from "./screens/WizardHost";
import { useStore } from "./state/store";

const log = getLogger("App");

// frob:ticket 01M6WA9WZW89EA826DSJCJ0197
// frob:ticket 01M6XAASMZX11EZ5NYC3FNTQ6Z
// frob:accept COV001 because="vitest tests exist (src/App.test.tsx, src/api/log.test.ts) but TypeScript test discovery needs grimble, not installed here"
/** Root component: probes the backend, shows connection state, the guided-run wizard and a persistent Doctor link. */
export function App(): React.JSX.Element {
  const connection = useStore((s) => s.connection);
  const setConnection = useStore((s) => s.setConnection);
  const visible = useDoctorRoute((s) => s.visible);
  const openDoctor = useDoctorRoute((s) => s.open);
  const closeDoctor = useDoctorRoute((s) => s.close);

  useEffect(() => {
    void getHealth().then((r) => {
      log.info("health probed", { ok: r.ok });
      setConnection(r.ok ? "up" : "down");
      if (!r.ok) openDoctorOnConnectionError();
    });
  }, [setConnection]);

  return (
    <>
      <nav aria-label="Tools">
        <button type="button" onClick={() => { if (visible) closeDoctor(); else openDoctor("nav"); }}>
          {visible ? "Close Doctor" : "Doctor"}
        </button>
      </nav>
      {visible ? <DoctorScreen /> : (
        <>
          <p>SADI - backend: {connection}</p>
          <WizardHost />
        </>
      )}
    </>
  );
}
