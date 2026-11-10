import { useEffect, useRef, useState } from "react";
import type { UseTraceOptions } from "./hooks/useTrace";
import { getHealth } from "./api/client";
import { getLogger } from "./api/log";
import { DoctorScreen } from "./doctor/DoctorScreen";
import { openDoctorOnConnectionError, useDoctorRoute } from "./doctor/useDoctorRoute";
import { WizardHost } from "./screens/WizardHost";
import { WeightPlanPanel } from "./screens/setup/WeightPlanPanel";
import { useTheme } from "./components/shell/theme";
import { DebugStrip } from "./components/instrument/DebugStrip";
import { InstrumentBar } from "./components/instrument/InstrumentBar";
import { useBackendFacts } from "./components/instrument/useBackendFacts";
import { FactsContext, RefreshFactsContext } from "./components/instrument/FactsContext";
import { LiveProvider } from "./state/LiveContext";
import { useProvenancePoll } from "./state/provenance";
import { useStore } from "./state/store";

const log = getLogger("App");

/** Health poll period in ms: how fast the UI notices a dead or recovered backend. */
export const HEALTH_POLL_MS = 3000;

// frob:ticket 01M727VHZTQHYABYCT6XTASEM1
// frob:ticket 01M6WA9WZW89EA826DSJCJ0197
// frob:ticket 01M6XAASMZX11EZ5NYC3FNTQ6Z
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
// frob:ticket 01M71VN3JDC5NDPJ2AW60KQX63
// frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5
// frob:accept COV001 because="vitest tests exist (src/App.test.tsx, src/api/log.test.ts) but TypeScript test discovery needs grimble, not installed here"
/** Root component: probes the backend, owns the one live stream subscription, shows the guided-run front panel and a persistent Doctor link. */
export function App({ trace }: { readonly trace?: UseTraceOptions } = {}): React.JSX.Element {
  const connection = useStore((s) => s.connection);
  const setConnection = useStore((s) => s.setConnection);
  const visible = useDoctorRoute((s) => s.visible);
  const openDoctor = useDoctorRoute((s) => s.open);
  const closeDoctor = useDoctorRoute((s) => s.close);
  const { theme, toggle } = useTheme();
  const [planning, setPlanning] = useState(false);
  useProvenancePoll();

  const { facts, refresh: refreshFacts } = useBackendFacts();

  const redirected = useRef(false);
  useEffect(() => {
    let live = true;
    const probe = (): void => {
      void getHealth().then((r) => {
        if (!live) return;
        const prev = useStore.getState().connection;
        const next = r.ok ? "up" : "down";
        if (prev !== next) log.info("health changed", { from: prev, to: next });
        setConnection(next);
        // Only the first failure opens the Doctor; later drops must not yank the user around.
        if (!r.ok && !redirected.current) { redirected.current = true; openDoctorOnConnectionError(); }
      });
    };
    probe();
    const id = setInterval(probe, HEALTH_POLL_MS);
    return () => { live = false; clearInterval(id); };
  }, [setConnection]);

  return (
    <FactsContext.Provider value={facts}>
    <RefreshFactsContext.Provider value={refreshFacts}>
    <LiveProvider {...(trace === undefined ? {} : { trace })}>
      <div className="app-top">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="brand">
            <span className="brand-name">SADI</span>
            <span className="brand-sub">Tensile test instrument</span>
          </div>
          <nav aria-label="Tools">
            <button type="button" aria-pressed={planning} onClick={() => { setPlanning((v) => !v); }}>
              {planning ? "Close weight plan" : "Weight plan"}
            </button>{" "}
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
      <InstrumentBar facts={facts} />
      </div>
      <DebugStrip facts={facts} backend={connection === "up" ? "[ok] up" : connection === "down" ? "(!) down" : "[..] checking"} />
      <div className="app-main">
        {visible ? <DoctorScreen /> : planning ? <WeightPlanPanel /> : <WizardHost />}
      </div>
    </LiveProvider>
    </RefreshFactsContext.Provider>
    </FactsContext.Provider>
  );
}
