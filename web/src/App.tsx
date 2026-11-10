import { useEffect } from "react";
import type { UseTraceOptions } from "./hooks/useTrace";
import { getHealth } from "./api/client";
import { getLogger } from "./api/log";
import { DoctorScreen } from "./doctor/DoctorScreen";
import { openDoctorOnConnectionError, useDoctorRoute } from "./doctor/useDoctorRoute";
import { WizardHost } from "./screens/WizardHost";
import { useTheme } from "./components/shell/theme";
import { LiveProvider } from "./state/LiveContext";
import { useStore } from "./state/store";

const log = getLogger("App");

// frob:ticket 01M6WA9WZW89EA826DSJCJ0197
// frob:ticket 01M6XAASMZX11EZ5NYC3FNTQ6Z
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:accept COV001 because="vitest tests exist (src/App.test.tsx, src/api/log.test.ts) but TypeScript test discovery needs grimble, not installed here"
/** Root component: probes the backend, owns the one live stream subscription, shows the guided-run front panel and a persistent Doctor link. */
export function App({ trace }: { readonly trace?: UseTraceOptions } = {}): React.JSX.Element {
  const connection = useStore((s) => s.connection);
  const setConnection = useStore((s) => s.setConnection);
  const visible = useDoctorRoute((s) => s.visible);
  const openDoctor = useDoctorRoute((s) => s.open);
  const closeDoctor = useDoctorRoute((s) => s.close);
  const { theme, toggle } = useTheme();

  useEffect(() => {
    void getHealth().then((r) => {
      log.info("health probed", { ok: r.ok });
      setConnection(r.ok ? "up" : "down");
      if (!r.ok) openDoctorOnConnectionError();
    });
  }, [setConnection]);

  return (
    <LiveProvider {...(trace === undefined ? {} : { trace })}>
      <header className="app-header">
        <div className="app-header-inner">
          <div className="brand">
            <span className="brand-name">SADI</span>
            <span className="brand-sub">Tensile test instrument</span>
          </div>
          <nav aria-label="Tools">
            <button type="button" onClick={() => { if (visible) closeDoctor(); else openDoctor("nav"); }}>
              {visible ? "Close Doctor" : "Doctor"}
            </button>
          </nav>
          <span className="pill" data-state={connection}>backend: {connection}</span>
          <button type="button" className="theme-toggle" aria-pressed={theme === "dark"} onClick={toggle}>
            {theme === "dark" ? "Light theme" : "Dark theme"}
          </button>
        </div>
      </header>
      <div className="app-main">
        {visible ? <DoctorScreen /> : <WizardHost />}
      </div>
    </LiveProvider>
  );
}
