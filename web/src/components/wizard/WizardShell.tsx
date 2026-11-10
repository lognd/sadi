// frob:ticket 01M727VHZTQHYABYCT6XTASEM1
// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:ticket 01M7274EKWS410XEGZGFD6HWHK
import { useCallback, useEffect, useRef, useState } from "react";
import { getLogger } from "../../api/log";
import { useKeyCapture } from "../../keys/useKeyCapture";
import type { KeyAction } from "../../keys/keymap";
import { useLive } from "../../state/LiveContext";
import { LiveTrace } from "../live/TraceCanvas";
import { useFacts } from "../instrument/FactsContext";
import { saveView } from "../status/saveView";
import { StatusBar } from "../status/StatusBar";
import { CloseSession } from "./CloseSession";
import { DoThisCard } from "./DoThisCard";
import { ErrorNotice } from "./ErrorNotice";
import { FrontPanel } from "./FrontPanel";
import { NextActionPanel } from "./NextActionPanel";
import { ShortcutList } from "./ShortcutList";
import { StepRail } from "./StepRail";
import type { WizardState } from "./types";
import { getWizard, postWizard, type WizardFailure, type WizardWrite } from "./wizardApi";

const log = getLogger("wizard.shell");

/** Shell props: work-area content comes from the step screens; live status comes from LiveProvider. */
export interface WizardShellProps {
  children?: React.ReactNode;
  /** Called for capture and window-nudge keys the shell does not handle itself. */
  onKeyAction?: (a: KeyAction) => void;
  nudgeActive?: boolean;
  /** Called whenever the rail is loaded or changes, so a host can pick the screen for the current step. */
  onWizard?: (w: WizardState) => void;
  /** When true, undo and redo keys go to `onKeyAction` instead of the shell (the work area owns history). */
  delegateUndo?: boolean;
  /** Called after the session was closed; defaults to reloading the page so it shows session setup. */
  onClosed?: () => void;
  /** Why Finish (button and Enter) is disabled right now, or null/absent when allowed. */
  finishBlockedWhy?: string | null;
  /** Rendered below the next-action panel (e.g. the live plot). */
  after?: React.ReactNode;
}

// frob:accept COV001 because="vitest tests exist (wizard.test.tsx, keymap.test.ts) but TypeScript test discovery needs grimble, not installed here"
/** Wizard shell: the front panel (step rail, step content, next action, live readout, live trace, status bar) plus keyboard capture. */
export function WizardShell({ children, onKeyAction, nudgeActive = false, onWizard, delegateUndo = false, onClosed, finishBlockedWhy = null, after }: WizardShellProps): React.JSX.Element {
  const { view } = useLive();
  const [wizard, setWizard] = useState<WizardState | null>(null);
  const [failure, setFailure] = useState<WizardFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const facts = useFacts();
  const [help, setHelp] = useState(true);
  const wizardCb = useRef(onWizard);
  wizardCb.current = onWizard;

  useEffect(() => {
    void getWizard().then((r) => {
      if (r.ok) { setWizard(r.value); wizardCb.current?.(r.value); }
      else { log.warn("wizard load failed"); setFailure(r.error); }
    });
  }, []);

  const currentId = wizard?.current ?? wizard?.rail.find((s) => s.status === "current")?.id;
  const write = useCallback(async (what: WizardWrite): Promise<void> => {
    setBusy(true);
    const stepped = what === "wizard/complete" || what === "wizard/skip" || what === "wizard/revert";
    const r = await postWizard(what, fetch, stepped ? currentId : undefined);
    setBusy(false);
    if (r.ok) {
      log.info("committed", { what, seq: r.value.seq });
      setWizard(r.value.wizard);
      wizardCb.current?.(r.value.wizard);
      setFailure(null);
    } else {
      log.warn("write failed", { what });
      setFailure(r.error);
    }
  }, [currentId]);

  const current = wizard?.rail.find((s) => s.status === "current") ?? null;
  const act = useCallback((a: KeyAction): void => {
    log.debug("action", { a });
    if ((a === "primary" || a === "finish-phase") && finishBlockedWhy !== null) log.info("finish ignored: minimum points not met", { why: finishBlockedWhy });
    else if (a === "primary" || a === "finish-phase") void write("wizard/complete");
    else if (delegateUndo && (a === "undo" || a === "redo")) onKeyAction?.(a);
    else if (a === "undo") void write("undo");
    else if (a === "redo") void write("redo");
    else if (a === "help") setHelp((h) => !h);
    else onKeyAction?.(a);
  }, [write, onKeyAction, delegateUndo, finishBlockedWhy]);
  useKeyCapture(act, nudgeActive);

  const index = wizard === null || current === null ? -1 : wizard.rail.indexOf(current);
  const title = wizard === null ? "Guided run" : current === null ? "All steps finished" : current.title;
  const subtitle = wizard === null || current === null ? null : `Step ${String(index + 1)} of ${String(wizard.rail.length)}`;
  const guide = wizard === null || current === null ? null : <DoThisCard phase={current.phase} index={index} total={wizard.rail.length} />;

  const closed = useCallback((): void => {
    if (onClosed !== undefined) onClosed(); else window.location.reload();
  }, [onClosed]);

  return (
    <FrontPanel
      title={title}
      actions={<CloseSession onClosed={closed} />}
      subtitle={subtitle}
      rail={wizard ? <StepRail rail={wizard.rail} /> : <p>Loading steps...</p>}
      guide={guide}
      after={after}
      shortcuts={help ? <details className="shortcuts"><summary>Keyboard shortcuts</summary><ShortcutList /></details> : null}
      live={<LiveTrace />}
      status={<StatusBar source={view.source} motion={view.motion} signal={view.signal} save={saveView(facts)} />}
      next={
        <NextActionPanel
          step={current}
          busy={busy}
          canSkip={current !== null}
          finishBlockedWhy={finishBlockedWhy}
          onPrimary={() => { void write("wizard/complete"); }}
          onSkip={() => { void write("wizard/skip"); }}
          finishedActions={<CloseSession label="Start another session" onClosed={closed} />}
        />
      }
    >
      {failure ? <ErrorNotice failure={failure} /> : null}
      {children}
    </FrontPanel>
  );
}
