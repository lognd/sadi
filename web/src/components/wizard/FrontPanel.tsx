// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5
// frob:ticket 01M7274EKWS410XEGZGFD6HWHK
// frob:accept COV001 because="covered by wizard.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"

/** Slots of the LabVIEW-style front panel; every wizard step fills the same slots. */
export interface FrontPanelProps {
  /** Current step title (the page heading). */
  readonly title: string;
  /** Short position text such as "Step 2 of 7", or null. */
  readonly subtitle: string | null;
  /** Left sidebar: the vertical step rail. */
  readonly rail: React.ReactNode;
  /** Left sidebar footer: keyboard shortcut list, or null when hidden. */
  readonly shortcuts: React.ReactNode;
  /** Right column: live readout and live trace cards. */
  readonly live: React.ReactNode;
  /** Right column footer: the status bar. */
  readonly status: React.ReactNode;
  /** Main column top: the "Do this" instructions card, or null. */
  readonly guide?: React.ReactNode;
  /** Main column footer: the prominent next-action panel. */
  readonly next: React.ReactNode;
  /** Header controls such as Close session, or null. */
  readonly actions?: React.ReactNode;
  /** Main column: the step content (capture card), shown between the guide and the next-action panel. */
  readonly children?: React.ReactNode;
  /** Main column, below the next-action panel: bulky extras such as the live plot. */
  readonly after?: React.ReactNode;
}

/** Persistent three-column layout: step rail left, step content centre, live instrument right. */
export function FrontPanel(p: FrontPanelProps): React.JSX.Element {
  return (
    <div className="front-panel">
      <header className="fp-head">
        <h1>{p.title}</h1>
        {p.subtitle === null ? null : <p className="fp-sub">{p.subtitle}</p>}
        {p.actions}
      </header>
      {/* DOM order is focus order: step content first, rail after; CSS grid-area keeps the layout (audit #39). */}
      <main className="fp-main">
        {p.guide}
        {p.children}
        {p.next}
        {p.after}
      </main>
      <div className="fp-side">
        {p.rail}
        {p.shortcuts}
      </div>
      <aside className="fp-live" aria-label="Live instrument">
        {p.live}
        {p.status}
      </aside>
    </div>
  );
}
