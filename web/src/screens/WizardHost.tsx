// frob:ticket 01M6XAZ42NR9WARFYVZMS85NR2
// frob:ticket 01M6WZCNF9F9XSPWCKB34JHSD9
// frob:ticket 01M6XA21KQE5WEXAN39683H4S9
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5
// frob:ticket 01M727YGXCC6ZFVHWHG64KFA7D
// frob:accept COV001 because="covered by WizardHost.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useCallback, useEffect, useState } from "react";
import { getLogger } from "../api/log";
import { enterRunPhase, isServerPhase } from "../api/runPhase";
import { ErrorNotice } from "../components/wizard/ErrorNotice";
import { WizardShell } from "../components/wizard/WizardShell";
import type { RailItem, WizardState } from "../components/wizard/types";
import { getWizard, type WizardFailure } from "../components/wizard/wizardApi";
import type { KeyAction } from "../keys/keymap";
import { ExportScreen, saveBlob } from "./export/ExportScreen";
import { DEFAULT_RUN_EXPORT, exportErrorText, fetchRunExport } from "./run/exportTrace";
import type { RunPhase } from "./run/phases";
import { RunScreen } from "./run/RunScreen";
import { ReviewScreen } from "./review/ReviewScreen";
import { ClampCheckPanel } from "./setup/ClampCheckPanel";
import { SessionSetup } from "./setup/SessionSetup";
import { useStore } from "../state/store";

const log = getLogger("screens.host");

/** Which screen a wizard step shows. */
export type ScreenKind = RunPhase | "setup" | "results" | "export" | "session";

const BY_PHASE: Readonly<Record<string, ScreenKind>> = {
  setup: "setup", calibration: "calibrate", tare: "tare", elastic: "elastic", plastic: "plastic",
  results: "results", export: "export",
};

/** Screen for the wizard's current step; a finished run (no current step) shows the export screen. */
export function screenFor(rail: readonly RailItem[]): ScreenKind {
  const cur = rail.find((s) => s.status === "current");
  if (cur === undefined) return "export";
  return BY_PHASE[cur.phase] ?? "setup";
}

/** Key handler for the export step: F3 downloads the CSV export (failures set `onError`; recorded data is untouched), other keys are ignored. */
function useExportKey(onError: (text: string | null) => void): (a: KeyAction) => void {
  return useCallback((a: KeyAction): void => {
    if (a !== "export") return;
    onError(null);
    void fetchRunExport(DEFAULT_RUN_EXPORT).then((r) => {
      if (r.ok) { saveBlob(r.value.blob, r.value.filename); log.info("export saved", { filename: r.value.filename }); }
      else {
        const text = exportErrorText(r.error);
        log.warn("export failed", { text });
        onError(text);
      }
    });
  }, [onError]);
}

/** Non-run steps: shell with rail around setup, review or export content. */
function StaticStep({ kind, onWizard, onClosed }: { kind: "setup" | "results" | "export"; onWizard: (w: WizardState) => void; onClosed: () => void }): React.JSX.Element {
  const [exportError, setExportError] = useState<string | null>(null);
  const onKey = useExportKey(setExportError);
  return (
    <WizardShell
      onWizard={onWizard}
      onClosed={onClosed}
      onKeyAction={kind === "export" ? onKey : undefined}
      delegateUndo={kind === "results"}
    >
      {exportError !== null && (
        <div role="alert" data-testid="export-error">
          <p>! {exportError}</p>
          <p>Your recorded data is safe on the server; use the format list below to download it.</p>
        </div>
      )}
      {kind === "setup" ? <ClampCheckPanel /> : kind === "results" ? <ReviewScreen /> : <ExportScreen />}
    </WizardShell>
  );
}

/** Whether a wizard load failure means the backend is unreachable (not a refusal), so the UI must not guess a screen. */
export function isBackendDown(f: WizardFailure): boolean {
  if (f.kind !== "transport") return false;
  return f.error.kind === "network" || (f.error.status >= 502 && f.error.status <= 504);
}

/** Guided-run host: picks the screen for the current wizard step and remounts it when the step changes. */
export function WizardHost(): React.JSX.Element {
  const [screen, setScreen] = useState<ScreenKind | null>(null);
  const onWizard = useCallback((w: WizardState): void => {
    const next = screenFor(w.rail);
    setScreen((prev) => {
      if (prev !== next) log.info("screen changed", { from: prev, to: next });
      return next;
    });
  }, []);

  const [down, setDown] = useState(false);
  const load = useCallback((): void => {
    void getWizard().then((r) => {
      if (r.ok) { setDown(false); onWizard(r.value); }
      else if (isBackendDown(r.error)) {
        log.warn("backend unreachable; waiting for it to return");
        setDown(true);
      }
      else if (r.error.kind === "problem" && r.error.problem.status === 409) {
        log.info("no open session; showing session setup");
        setScreen("session");
      } else { log.warn("initial wizard load failed; showing setup"); setScreen("setup"); }
    });
  }, [onWizard]);

  useEffect(() => { load(); }, [load]);

  // Reload once when the connection recovers after the initial load found the backend down.
  const connection = useStore((st) => st.connection);
  useEffect(() => {
    if (down && connection === "up") { log.info("backend back; reloading wizard"); load(); }
  }, [down, connection, load]);

  const [phaseError, setPhaseError] = useState<WizardFailure | null>(null);
  useEffect(() => {
    setPhaseError(null);
    if (screen === null || !isServerPhase(screen)) return;
    let live = true;
    void enterRunPhase(screen).then((r) => {
      if (!live) return;
      if (!r.ok) { log.warn("run phase refused", { screen }); setPhaseError(r.error); }
    });
    return () => { live = false; };
  }, [screen]);

  if (down && screen === null) return <p role="alert" data-testid="backend-down">The SADI backend is not reachable. Waiting for it to come back; this page reloads by itself.</p>;
  if (screen === null) return <p>Loading steps...</p>;
  if (screen === "session") return <SessionSetup onOpened={load} />;
  if (screen === "setup" || screen === "results" || screen === "export") {
    return <StaticStep key={screen} kind={screen} onWizard={onWizard} onClosed={load} />;
  }
  return (
    <>
      {phaseError !== null && <ErrorNotice failure={phaseError} />}
      <RunScreen key={screen} phase={screen} onWizard={onWizard} />
    </>
  );
}
