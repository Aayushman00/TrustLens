import { useEffect, useId, useRef } from "react";
import { EvidenceChip, type EvidenceRef } from "./EvidenceChip";

export type TraceLayer = "score" | "assessment" | "evidence";
export interface TraceLevel {
  layer: TraceLayer;
  heading: string;
  value?: string;
  rows?: [string, string][];
  evidence?: EvidenceRef[];
  raw?: unknown;
}
export interface TraceChain { title: string; levels: TraceLevel[] }

const LAYER_NAME: Record<TraceLayer, string> = {
  score: "FRIES score",
  assessment: "Risk assessment",
  evidence: "Evidence",
};

/** Non-modal side sheet: the page stays inspectable while tracing.
 * Summary → evidence (1 click) → raw JSON (2 clicks). */
export function TracePanel({ chain, onClose }: { chain: TraceChain | null; onClose: () => void }) {
  const headingId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; });

  useEffect(() => {
    if (!chain) return;
    const returnTo = document.activeElement as HTMLElement | null;
    headingRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeRef.current(); };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      returnTo?.focus?.();
    };
  }, [chain]);

  if (!chain) return null;
  return (
    <aside className="tl-trace" role="dialog" aria-modal="false" aria-labelledby={headingId}>
      <header className="tl-trace__head">
        <h2 id={headingId} ref={headingRef} tabIndex={-1} className="tl-display">{chain.title}</h2>
        <button type="button" onClick={onClose} aria-label="Close trace">✕</button>
      </header>
      <ol className="tl-trace__chain">
        {chain.levels.map((level, i) => (
          <li key={i} className={`tl-trace__level tl-trace__level--${level.layer}`}>
            <span className="tl-trace__layer">{LAYER_NAME[level.layer]}</span>
            <h3 className="tl-trace__heading">{level.heading}</h3>
            {level.value && <p className="tl-trace__value num">{level.value}</p>}
            {level.rows && (
              <dl className="tl-trace__rows">
                {level.rows.map(([k, v]) => (
                  <div key={k}><dt>{k}</dt><dd className="num">{v}</dd></div>
                ))}
              </dl>
            )}
            {level.evidence?.map((ev, j) => <EvidenceChip key={`${i}-${j}`} evidence={ev} />)}
            {level.raw !== undefined && (
              <details className="tl-trace__raw">
                <summary>Raw JSON</summary>
                <pre>{JSON.stringify(level.raw, null, 2)}</pre>
              </details>
            )}
          </li>
        ))}
      </ol>
    </aside>
  );
}
