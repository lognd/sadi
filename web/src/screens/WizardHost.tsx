// frob:ticket 01M6WZCNF9F9XSPWCKB34JHSD9
// frob:accept COV001 because="covered by WizardHost.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useCallback, useEffect, useState } from "react";
import { getLogger } from "../api/log";
import { WizardShell } from "../components/wizard/WizardShell";
import type { RailItem, WizardState } from "../components/wizard/types";
import { getWizard } from "../components/wizard/wizardApi";
import type { KeyAction } from "../keys/keymap";
import { useStore } from "../state/store";
import { ExportScreen, saveBlob } from "./export/ExportScreen";
import { DEFAULT_RUN_EXPORT, exportErrorText, fetchRunExport } from "./run/exportTrace";
import type { RunPhase } from "./run/phases";
import { RunScreen } from "./run/RunScreen";
import { ReviewScreen } from "./review/ReviewScreen";

const log = getLogger("screens.host");

/** Which screen a wizard step shows. */
export type ScreenKind = RunPhase | "setup" | "results" | "export";

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

/** Setup step body: points the operator at the next action; the shell's panel carries Enter and Skip. */
function SetupBody(): React.JSX.Element {
  return (
    <section aria-label="Setup">
      <h2>Setup</h2>
      <p>Check the rig and the specimen. Press Enter when ready, or use Skip this step to continue without the setup check.</p>
    </section>
  );
}

/** Key handler for the export step: F3 downloads the CSV export, other keys are ignored. */
function useExportKey(): (a: KeyAction) => void {
  return useCallback((a: KeyAction): void => {
    if (a !== "export") return;
    void fetchRunExport(DEFAULT_RUN_EXPORT).then((r) => {
      if (r.ok) { saveBlob(r.value.blob, r.value.filename); log.info("export saved", { filename: r.value.filename }); }
      else log.warn("export failed", { text: exportErrorText(r.error) });
    });
  }, []);
}

/** Non-run steps: shell with rail around setup, review or export content. */
function StaticStep({ kind, onWizard }: { kind: "setup" | "results" | "export"; onWizard: (w: WizardState) => void }): React.JSX.Element {
  const connection = useStore((s) => s.connection);
  const onKey = useExportKey();
  return (
    <WizardShell
      status={{ source: connection === "up" ? "connected" : "disconnected", motion: "unknown", signal: "ok" }}
      onWizard={onWizard}
      onKeyAction={kind === "export" ? onKey : undefined}
      delegateUndo={kind === "results"}
    >
      {kind === "setup" ? <SetupBody /> : kind === "results" ? <ReviewScreen /> : <ExportScreen />}
    </WizardShell>
  );
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

  useEffect(() => {
    void getWizard().then((r) => {
      if (r.ok) onWizard(r.value);
      else { log.warn("initial wizard load failed; showing setup"); setScreen("setup"); }
    });
  }, [onWizard]);

  if (screen === null) return <p>Loading steps...</p>;
  if (screen === "setup" || screen === "results" || screen === "export") {
    return <StaticStep key={screen} kind={screen} onWizard={onWizard} />;
  }
  return <RunScreen key={screen} phase={screen} onWizard={onWizard} />;
}
