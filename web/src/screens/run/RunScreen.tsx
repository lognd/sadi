// frob:ticket 01M72TEVXXFP3PZ84SABZEDX7H
// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// frob:ticket 01M6WWN96C55R68VNZF2D1NB2V
// frob:ticket 01M6X9NXWB7KW3ZGQP02KDWN8N
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
// frob:ticket 01M7274EKWS410XEGZGFD6HWHK
// frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
// frob:accept COV001 because="covered by RunScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useCallback, useEffect, useRef, useState } from "react";
import { getLogger } from "../../api/log";
import { WizardShell } from "../../components/wizard/WizardShell";
import { useLive } from "../../state/LiveContext";
import type { KeyAction } from "../../keys/keymap";
import type { WizardState } from "../../components/wizard/types";
import { DEFAULT_RUN_EXPORT, exportErrorText, fetchRunExport } from "./exportTrace";
import { postLoadChange } from "./loadChange";
import { buildBody, buildSpecimenBody, capturedMessage, decide, newRequestId, postCapture, WHY_SAME_LOAD, type Confirm } from "./capture";
import type { RunPhase } from "./phases";
import { collectInputs, splitSpecimen } from "./inputFields";
import { RunPlot, RunView, type PhasePlot } from "./RunView";
import { getPoints } from "../review/api";
import { guidanceText } from "./guidance";
import { SuggestedWeightPanel } from "./SuggestedWeightPanel";
import { countPhasePoints, finishBlockedWhy } from "./pointCount";

const log = getLogger("screens.run");

/** Save a blob through a temporary link; browser only. */
function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** Props of the run screen. */
export interface RunScreenProps {
  readonly phase: RunPhase;
  /** Phase plot data, fed by the host after each capture. */
  readonly plot?: PhasePlot | null;
  /** Typed inputs sent with a capture (voltage-independent: length, mass, ...). */
  readonly inputs?: Readonly<Record<string, unknown>>;
  /** Called after the server accepted a capture. */
  readonly onCaptured?: () => void;
  /** Server export format F3 downloads (default lctt-csv). */
  readonly exportFormat?: string;
  /** Receives the downloaded export; the default saves it through a temporary link (browser only). */
  readonly onExport?: (blob: Blob, filename: string) => void;
  /** Forwarded to the wizard shell: called when the rail changes. */
  readonly onWizard?: (w: WizardState) => void;
  readonly fetchImpl?: typeof fetch;
}

/** Live run screen for calibrate, tare, elastic and plastic: wizard shell, live trace, accept key, confirmation. */
export function RunScreen(p: RunScreenProps): React.JSX.Element {
  const live = useLive();
  const [confirm, setConfirm] = useState<Confirm>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [fields, setFields] = useState<Readonly<Record<string, string>>>({});
  const [savedTick, setSavedTick] = useState(0);
  const [pointCount, setPointCount] = useState<number | null>(null);
  const inFlight = useRef(false);
  // frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
  const attemptId = useRef<string | null>(null); // reused on retry until the capture succeeds
  const loadRecorded = useRef(false); // true after a capture until the load change is marked
  const { view, side } = live;
  const onField = useCallback((k: string, v: string): void => { attemptId.current = null; setFields((f) => ({ ...f, [k]: v })); }, []);
  // Count the saved points for this step from the server so Finish stays gated correctly after a reload.
  useEffect(() => {
    let alive = true;
    void getPoints(p.fetchImpl).then((r) => {
      if (!alive) return;
      if (r.ok) setPointCount(countPhasePoints(r.value, p.phase));
      else log.warn("point count unavailable; Finish not gated");
    });
    return () => { alive = false; };
  }, [p.phase, p.fetchImpl, savedTick]);
  const preview = decide(view, false, "idle");
  const blockedWhy = preview.kind === "blocked" ? preview.why : null;

  const captureOnce = useCallback(async (early: boolean): Promise<void> => {
    const typed = collectInputs(p.phase, fields, view.recent?.mean ?? view.volts, view.recent ?? null);
    if (!typed.ok) { setConfirm("idle"); setMessage(typed.error.join(" ")); return; }
    const { own, specimen } = splitSpecimen(p.phase, typed.value);
    if (specimen !== null) {
      const sp = await postCapture(buildSpecimenBody(specimen, side.rawSeq, view), p.fetchImpl);
      if (!sp.ok) {
        setConfirm("idle");
        setMessage(sp.error.kind === "network" ? `Network error: ${sp.error.message}. Check the connection, then try again.` : `Specimen capture refused (HTTP ${String(sp.error.status)}). ${sp.error.body}`);
        return;
      }
    }
    attemptId.current ??= newRequestId();
    const r = await postCapture(buildBody(p.phase, { ...own, ...p.inputs }, side.rawSeq, view, early, attemptId.current), p.fetchImpl);
    setConfirm("idle");
    if (r.ok) { attemptId.current = null; loadRecorded.current = true; setMessage(capturedMessage(r.value.summary)); setSavedTick((n) => n + 1); p.onCaptured?.(); }
    else {
      if (r.error.kind !== "network" && r.error.status === 409) attemptId.current = null; // id used for a different point: next try gets a fresh id
      setMessage(r.error.kind === "network" ? `Network error: ${r.error.message}. Check the connection, then try again.` : `Capture refused (HTTP ${String(r.error.status)}). ${r.error.body}`);
    }
  }, [p, side.rawSeq, view, fields]);

  const capture = useCallback(async (early: boolean): Promise<void> => {
    if (inFlight.current) { log.warn("capture ignored: one already in flight"); return; }
    inFlight.current = true;
    try { await captureOnce(early); } finally { inFlight.current = false; }
  }, [captureOnce]);

  const accept = useCallback((early: boolean): void => {
    if (loadRecorded.current) { log.info("accept ignored: load already recorded"); setMessage(WHY_SAME_LOAD); setConfirm("idle"); return; }
    const d = decide(view, early, confirm);
    log.info("accept", { early, decision: d.kind });
    if (d.kind === "blocked") { setMessage(d.why); setConfirm("idle"); }
    else if (d.kind === "confirm-early") setConfirm("asking");
    else void capture(d.kind === "capture-early");
  }, [view, confirm, capture]);

  const markLoadChange = useCallback(async (): Promise<void> => {
    const r = await postLoadChange(p.fetchImpl);
    if (r.ok) { loadRecorded.current = false; attemptId.current = null; }
    if (r.ok) setMessage("Load change marked; wait for the reading to settle.");
    else setMessage(r.error.kind === "network" ? `Network error: ${r.error.message}. Check the connection, then try again.` : `Load change refused (HTTP ${String(r.error.status)}). ${r.error.body}`);
  }, [p.fetchImpl]);

  const doExport = useCallback(async (): Promise<void> => {
    const r = await fetchRunExport(p.exportFormat ?? DEFAULT_RUN_EXPORT, p.fetchImpl);
    if (!r.ok) { setMessage(exportErrorText(r.error)); return; }
    (p.onExport ?? saveBlob)(r.value.blob, r.value.filename);
    setMessage(`Exported ${r.value.filename}`);
    log.info("exported", { filename: r.value.filename });
  }, [p]);

  const onKey = useCallback((a: KeyAction): void => {
    if (a === "accept") accept(false);
    else if (a === "accept-unsettled") accept(true);
    else if (a === "cancel") setConfirm("idle");
    else if (a === "export") void doExport();
  }, [accept, doExport]);

  return (
    <WizardShell onKeyAction={onKey} onWizard={p.onWizard} finishBlockedWhy={finishBlockedWhy(p.phase, pointCount)} after={<RunPlot plot={p.plot ?? null} />}>
      {side.guidance != null && (
        <p data-testid="guidance-note">
          {guidanceText(side.guidance.nextAction)}
        </p>
      )}
      {(p.phase === "elastic" || p.phase === "plastic" || p.phase === "calibrate") && (
        <SuggestedWeightPanel phase={p.phase === "plastic" ? "yield" : p.phase === "calibrate" ? "lvdt_cal" : "elastic"} tick={savedTick} fetchImpl={p.fetchImpl} />
      )}
      <RunView
        phase={p.phase} view={view} pointCount={pointCount}
        fields={fields} onField={onField}
        blockedWhy={blockedWhy} confirming={confirm === "asking"} message={message ?? live.notice}
        onAccept={() => { accept(false); }} onLoadChange={() => { void markLoadChange(); }} onConfirmEarly={() => { accept(true); }}
        onCancelEarly={() => { setConfirm("idle"); }}
      />
    </WizardShell>
  );
}
