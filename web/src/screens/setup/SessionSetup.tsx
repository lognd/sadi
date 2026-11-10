// frob:ticket 01M6WZX63YFEAYQTPJXE2BTRN2
// frob:ticket 01M729FVNSJCVAHK4XBSG9NBYC
// frob:ticket 01M72T4R3X8833V8Z978SH4481
// frob:accept COV001 because="covered by SessionSetup.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useEffect, useState } from "react";
import { getLogger } from "../../api/log";
import { useRefreshFacts } from "../../components/instrument/FactsContext";
import { saveBlob } from "../export/ExportScreen";
import {
  createSession, csvFormatFor, downloadClosedExport, downloadFailureText, failureText, listLabs, listSessions, resumeSession,
  type LabInfo, type SessionSummary,
} from "./sessionApi";

const log = getLogger("setup.session");

/** Build the specimen map from the form, dropping blank fields. */
export function specimenFrom(fields: Readonly<Record<string, string>>): Record<string, string> {
  return Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, v.trim()] as const).filter(([, v]) => v !== ""));
}

/** Slug the server accepts: lowercase letters, digits and dashes. */
export function slugFrom(text: string): string {
  const s = text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return s === "" ? "session" : s;
}

/** Plain display names per lab id (ids stay stable; server titles are technical). */
const LAB_NAMES: Readonly<Record<string, string>> = { lctt: "Copper wire tension test (weights and displacement)" };

/** Display name for a lab id, falling back to the server title. */
function labName(id: string): string { return LAB_NAMES[id] ?? id; }

/** Option text for a lab. */
function labTitle(l: LabInfo): string { return LAB_NAMES[l.id] ?? l.title; }

/** True for sessions whose log may end in a torn tail (interrupted writer or failed fold). */
// frob:ticket 01M727965F98C8FB295P7A7FRS
export function isRecoverable(state: string): boolean {
  return state === "open" || state === "incomplete";
}

/**
 * Setup screen shown when no session is open: resume an existing one or start a new one.
 * Resuming makes a new version and creating gets a new id, so existing data is never overwritten.
 */
export function SessionSetup({ onOpened }: { onOpened: () => void }): React.JSX.Element {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [labs, setLabs] = useState<LabInfo[]>([]);
  const [lab, setLab] = useState("");
  const [name, setName] = useState("");
  const [material, setMaterial] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const refreshFacts = useRefreshFacts();

  useEffect(() => {
    void listSessions().then((r) => {
      if (r.ok) setSessions(r.value);
      else { setSessions([]); setMessage(failureText(r.error)); }
    });
    void listLabs().then((r) => {
      if (r.ok) { setLabs(r.value); setLab((cur) => (cur === "" ? (r.value[0]?.id ?? "") : cur)); }
      else setMessage(failureText(r.error));
    });
  }, []);

  const finish = (r: { ok: boolean; error?: unknown }, what: string): void => {
    setPending(null);
    if (r.ok) { log.info("session opened", { what }); refreshFacts(); onOpened(); }
  };

  const resume = (s: SessionSummary): void => {
    if (pending !== null) return;
    setPending(s.name);
    setMessage("");
    void resumeSession(s.name).then((r) => {
      if (!r.ok) setMessage(failureText(r.error));
      finish(r, `resume ${s.name}`);
    });
  };

  const download = (s: SessionSummary): void => {
    const fmt = csvFormatFor(s.lab);
    if (pending !== null || fmt === null) return;
    setPending(s.name);
    setMessage("");
    void downloadClosedExport(s.name, fmt).then((r) => {
      setPending(null);
      if (r.ok) { saveBlob(r.value.blob, r.value.filename); log.info("closed session downloaded", { name: s.name }); }
      else setMessage(downloadFailureText(r.error));
    });
  };

  const create = (e: React.SyntheticEvent): void => {
    e.preventDefault();
    if (pending !== null || lab === "") return;
    setPending("new");
    setMessage("");
    const body = { lab, slug: slugFrom(name), specimen: specimenFrom({ name, material }) };
    void createSession(body).then((r) => {
      if (!r.ok) setMessage(failureText(r.error));
      finish(r, `create ${body.slug}`);
    });
  };

  return (
    <section aria-label="Session setup" className="setup">
      <h2>Start a tension test</h2>
      <p className="setup-intro">
        This lab pulls a copper wire with weights and measures how much it stretches. From that it works out
        how stiff the wire is and where it starts to deform for good.
      </p>
      <div className="setup-cols">
        <div className="setup-new">
          <h3>New session</h3>
          <form onSubmit={create} aria-label="New session" className="stack">
            <label>Lab
              <select value={lab} onChange={(e) => { setLab(e.target.value); }}>
                {labs.map((l) => <option key={l.id} value={l.id}>{labTitle(l)}</option>)}
              </select>
              <small>Which experiment to run.</small>
            </label>
            <label>Specimen name
              <input value={name} onChange={(e) => { setName(e.target.value); }} placeholder="cu-wire-1" autoFocus />
              <small>Used to name the saved files, e.g. cu-wire-1.</small>
            </label>
            <label>Material
              <input value={material} onChange={(e) => { setMaterial(e.target.value); }} placeholder="copper" />
              <small>Optional; recorded with the results.</small>
            </label>
            <button type="submit" className="btn btn-primary" data-variant="primary" disabled={pending !== null || lab === ""}>Create session</button>
          </form>
          {labs.length === 0 ? <p>No labs are registered, so a new session cannot be created.</p> : null}
        </div>
        <div className="setup-side">
          <h3>What happens next</h3>
          <ol className="next-steps">
            <li>Clamp the wire and check it does not slip.</li>
            <li>Calibrate and tare the displacement sensor.</li>
            <li>Add weights and capture each settled reading.</li>
            <li>Read the results and export the data.</li>
          </ol>
          <h3>Resume a session</h3>
          {sessions === null ? <p>Loading sessions...</p> : sessions.length === 0 ? <p>No saved sessions.</p> : (
            <ul aria-label="Existing sessions" className="session-list">
              {sessions.map((s) => (
                <li key={s.name}>
                  <span>{s.name} {s.spill_import != null && s.parent == null ? <strong role="note" data-testid={`unknown-${s.name}`}>Provenance unknown (recovered without its original session)</strong> : s.provenance.synthetic ? <strong className="synthetic-badge" role="note" data-testid={`synthetic-${s.name}`}>SYNTHETIC</strong> : null}{" "}
                    {s.spill_import === "fragment" ? <small role="note" data-testid={`fragment-${s.name}`}>Recovered fragment (only the last few records; the full data is in {s.parent ?? "the original session"})</small> : null}
                    {s.spill_import === "joined" ? <small role="note" data-testid={`joined-${s.name}`}>Recovered (complete)</small> : null}{" "}<small>({labName(s.lab)}, v{s.version}, {s.state})</small>{" "}
                    {s.latest ? null : <small role="note" data-testid={`newer-${s.name}`}>Newer work exists: {s.latest_name ?? "a later version"}. Resume that one unless you want this older copy.</small>}</span>
                  <button type="button" disabled={pending !== null} onClick={() => { resume(s); }}>
                    Resume {s.name}
                  </button>
                  {s.state === "closed" && csvFormatFor(s.lab) !== null ? (
                    <button type="button" disabled={pending !== null} onClick={() => { download(s); }}>
                      Download {s.name}
                    </button>
                  ) : null}
                  {isRecoverable(s.state) && csvFormatFor(s.lab) !== null ? (
                    <button type="button" disabled={pending !== null} onClick={() => { download(s); }}>
                      Download recovered data (may be missing the last few seconds): {s.name}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <p className="data-safety"><small>Your data is safe: resuming makes a new version, the original is kept, and nothing is ever overwritten.</small></p>
      <p role="status">{message}</p>
    </section>
  );
}
