// frob:ticket 01M6WZX63YFEAYQTPJXE2BTRN2
// frob:accept COV001 because="covered by SessionSetup.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useEffect, useState } from "react";
import { getLogger } from "../../api/log";
import {
  createSession, failureText, listLabs, listSessions, resumeSession,
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
    if (r.ok) { log.info("session opened", { what }); onOpened(); }
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
    <section aria-label="Session setup">
      <h2>Session setup</h2>
      <p>No session is open. Resume an existing session (it is saved as a new version; the original is kept) or start a new one.</p>
      <h3>Existing sessions</h3>
      {sessions === null ? <p>Loading sessions...</p> : sessions.length === 0 ? <p>No saved sessions.</p> : (
        <ul aria-label="Existing sessions">
          {sessions.map((s) => (
            <li key={s.name}>
              <span>{s.name} ({s.lab}, v{s.version}, {s.state})</span>{" "}
              <button type="button" disabled={pending !== null} onClick={() => { resume(s); }}>
                Resume {s.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      <h3>New session</h3>
      <form onSubmit={create} aria-label="New session">
        <label>Lab{" "}
          <select value={lab} onChange={(e) => { setLab(e.target.value); }}>
            {labs.map((l) => <option key={l.id} value={l.id}>{l.title}</option>)}
          </select>
        </label>{" "}
        <label>Specimen name{" "}
          <input value={name} onChange={(e) => { setName(e.target.value); }} autoFocus />
        </label>{" "}
        <label>Material{" "}
          <input value={material} onChange={(e) => { setMaterial(e.target.value); }} />
        </label>{" "}
        <button type="submit" disabled={pending !== null || lab === ""}>Create session</button>
      </form>
      {labs.length === 0 ? <p>No labs are registered, so a new session cannot be created.</p> : null}
      <p role="status">{message}</p>
    </section>
  );
}
