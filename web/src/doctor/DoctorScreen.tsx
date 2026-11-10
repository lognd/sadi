import { useCallback, useEffect, useState } from "react";
import { getDoctor, runDoctorCheck, type ApiError } from "../api/client";
import { getLogger } from "../api/log";
import type { Result } from "../api/result";
import type { CheckResult, DoctorReport } from "./types";

// frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5

const log = getLogger("doctor.screen");

/** Client functions the screen needs; injectable so tests can mock the API. */
export interface DoctorApi {
  list: () => Promise<Result<DoctorReport, ApiError>>;
  run: (id: string) => Promise<Result<CheckResult, ApiError>>;
}

const defaultApi: DoctorApi = {
  list: () => getDoctor(),
  run: (id) => runDoctorCheck(id),
};

/** Numbered, expandable fix steps for one check. */
export function FixSteps({ result }: { result: CheckResult }): React.JSX.Element | null {
  const rem = result.remediation;
  if (!rem) return null;
  return (
    <section aria-label={`Fix steps for ${result.id}`}>
      <p>{rem.summary}</p>
      <ol>
        {rem.steps.map((s, i) => (
          <li key={i}>
            <div>{s.text}</div>
            {s.commands.map((c, j) => (
              <pre key={j}>{c.line}</pre>
            ))}
            <div>Expect: {s.expect}</div>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Verdict banner: overall verdict, per-status counts and the first thing to do (audit #33). */
export function VerdictBanner({ summary, results }: { summary: DoctorReport["summary"]; results: readonly CheckResult[] }): React.JSX.Element {
  const n = (st: CheckResult["status"]): number => results.filter((c) => c.status === st).length;
  return (
    <section role="status" aria-label="Doctor verdict" data-verdict={summary.verdict}>
      <strong>Verdict: {summary.verdict}</strong>{" "}
      <span>{n("pass")} passed, {n("warn")} warnings, {n("fail")} failed, {n("skip")} skipped</span>
      {summary.first_action ? <p>Do this first: {summary.first_action}</p> : null}
    </section>
  );
}

/** Doctor screen: lists checks with status, expandable fix steps and per-check re-run. */
export function DoctorScreen({ api = defaultApi }: { api?: DoctorApi }): React.JSX.Element {
  const [results, setResults] = useState<CheckResult[]>([]);
  const [summary, setSummary] = useState<DoctorReport["summary"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());

  const load = useCallback(async () => {
    const r = await api.list();
    if (!r.ok) {
      log.warn("list failed", { error: r.error });
      setError("Could not load doctor results");
      return;
    }
    log.info("results loaded", { count: r.value.results.length });
    setError(null);
    setResults(r.value.results);
    setSummary(r.value.summary);
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (id: string): void => {
    setOpen((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  };

  const rerun = async (id: string): Promise<void> => {
    setBusy((p) => new Set(p).add(id));
    const r = await api.run(id);
    setBusy((p) => {
      const next = new Set(p);
      next.delete(id);
      return next;
    });
    if (!r.ok) {
      log.warn("re-run failed", { id, error: r.error });
      setError(`Re-run of ${id} failed`);
      return;
    }
    log.info("re-run done", { id, status: r.value.status });
    setError(null);
    setResults((prev) => prev.map((c) => (c.id === id ? r.value : c)));
  };

  return (
    <main aria-label="Doctor">
      <h1>Doctor</h1>
      {error !== null && <p role="alert">{error}</p>}
      {summary !== null && <VerdictBanner summary={summary} results={results} />}
      <ul>
        {results.map((c) => (
          <li key={c.id} data-status={c.status}>
            <span>[{c.status}]</span> <strong>{c.id}</strong> {c.title} - {c.headline}
            {c.remediation && (
              <button type="button" aria-expanded={open.has(c.id)} onClick={() => { toggle(c.id); }}>
                {open.has(c.id) ? "Hide fix steps" : "Show fix steps"}
              </button>
            )}
            <button type="button" disabled={busy.has(c.id)} onClick={() => { void rerun(c.id); }}>
              Re-run {c.id}
            </button>
            {open.has(c.id) && <FixSteps result={c} />}
          </li>
        ))}
      </ul>
    </main>
  );
}
