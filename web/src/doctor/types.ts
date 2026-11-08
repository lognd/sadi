/** Wire types mirroring python/sadi/doctor/schema.py (hand-written until the server exposes OpenAPI). */
export type Status = "pass" | "warn" | "fail" | "skip";
export type Severity = "blocker" | "error" | "warning" | "info";
export type StepKind = "action" | "manual" | "verify";
export type Shell = "sh" | "powershell" | "cmd";

/** One copy-paste command line of a step. */
export interface Command {
  shell: Shell;
  line: string;
  context?: string | null;
  fixable?: boolean;
}

/** One numbered remediation step. */
export interface Step {
  kind: StepKind;
  text: string;
  commands: Command[];
  expect: string;
  mutates?: string;
  changes?: string | null;
  if_not?: string | null;
  alt?: string | null;
}

/** Ordered fix steps for one failing check. */
export interface Remediation {
  check_id: string;
  mode: string;
  os: string;
  summary: string;
  steps: Step[];
  docs: string[];
}

/** Outcome of one check (subset of CheckResult the UI needs). */
export interface CheckResult {
  id: string;
  title: string;
  layer: string;
  severity: Severity;
  status: Status;
  headline: string;
  mode?: string | null;
  skip_reason?: string | null;
  remediation?: Remediation | null;
  duration_ms: number;
}

/** Whole doctor run as returned by GET /api/doctor. */
export interface DoctorReport {
  schema_version: 1;
  results: CheckResult[];
  summary: { verdict: "ready" | "degraded" | "blocked"; first_action?: string | null };
}
