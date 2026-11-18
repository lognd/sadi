// frob:ticket 01M72ZDQGAN0VQRKHM489H28J1
// frob:ticket 01M6XAASMZX11EZ5NYC3FNTQ6Z
// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
import type { RailItem, StepStatus } from "./types";

const GLYPH: Record<StepStatus, string> = { done: "[x]", skipped: "[-]", current: "[>]", locked: "[ ]" };
const WORD: Record<StepStatus, string> = { done: "done", skipped: "skipped", current: "current", locked: "upcoming" };

/** Plain-language one-line description per wizard phase, shown under the step title. */
export const STEP_BLURB: Readonly<Record<string, string>> = {
  setup: "Check the clamps hold the specimen without slipping.",
  calibration: "Teach the instrument what a volt of LVDT output means in length.",
  tare: "Record the empty reading before any load is applied.",
  elastic: "Add load in small steps and capture each settled point.",
  plastic: "Keep loading past the knee to see the specimen yield.",
  results: "Review the fitted values with their uncertainties.",
  export: "Save the run as a file or figure.",
};

/** Persistent vertical step rail: glyph plus word and a short description per step; the current step is the tab stop and every step can be viewed read-only with its View button (viewing never advances the run), marked aria-current. */
export function StepRail({ rail, viewing = null, onView }: { rail: readonly RailItem[]; viewing?: string | null; onView?: (id: string | null) => void }): React.JSX.Element {
  return (
    <nav aria-label="Steps">
      <ol className="step-rail">
        {rail.map((s, i) => (
          <li
            key={s.id}
            data-status={s.status}
            data-viewing={viewing === s.id ? "true" : undefined}
            aria-current={s.status === "current" ? "step" : undefined}
            tabIndex={s.status === "current" ? 0 : undefined}
          >
            <span className="step-glyph" aria-hidden="true">{GLYPH[s.status]}</span>
            <span className="step-body">
              <span className="step-title">{i + 1}. {s.title}</span>{" "}
              <span className="step-state">({WORD[s.status]})</span>
              <span className="step-blurb">{STEP_BLURB[s.phase] ?? s.hint}</span>
              {s.status === "skipped" && s.hint !== "" ? <em> {s.hint}</em> : null}
              {onView === undefined ? null : (
                <button type="button" className="step-view" aria-pressed={viewing === s.id} onClick={() => { onView(s.status === "current" || viewing === s.id ? null : s.id); }}>
                  {s.status === "current" ? "Show" : viewing === s.id ? "Close view" : "View"} {s.title}
                </button>
              )}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
