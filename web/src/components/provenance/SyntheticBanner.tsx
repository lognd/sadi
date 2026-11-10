// frob:ticket ~60KQX63
import { isSynthetic, SYNTHETIC_LABEL, useProvenance, type DataProvenance } from "../../state/provenance";

/** The one loud banner for synthetic data: icon + text + pattern; renders nothing for real data. */
export function SyntheticBanner({ provenance, compact = false }: { readonly provenance?: DataProvenance | null; readonly compact?: boolean }): React.JSX.Element | null {
  const stored = useProvenance((s) => s.provenance);
  const p = provenance === undefined ? stored : provenance;
  if (!isSynthetic(p)) return null;
  const label = p?.label ? p.label : SYNTHETIC_LABEL;
  return (
    <div className="synthetic-banner" data-compact={compact ? "true" : "false"} role="status" aria-live="polite" data-testid="synthetic-banner" title={p?.warning}>
      <svg className="synthetic-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M12 2 L23 21 H1 Z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        <path d="M12 9 V15 M12 17.5 V18.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <strong>{label}</strong>
      {compact || !p?.warning ? null : <span className="synthetic-warning">{p.warning}</span>}
    </div>
  );
}
