/**
 * Small labeled tag distinguishing WHAT KIND of statement a value is —
 * observed evidence, a derived metric, a gate/rule, a risk decision, human
 * judgment, a limitation, or unavailable/withheld. Used throughout the
 * Report page's Evidence Traceability section so a reader never has to
 * guess whether a number was measured, computed, or entered by a person.
 */
export type ChainKind =
  | "evidence"
  | "metric"
  | "gate"
  | "risk"
  | "human"
  | "limitation"
  | "unavailable";

const LABELS: Record<ChainKind, string> = {
  evidence: "Observed evidence",
  metric: "Derived metric",
  gate: "Gate / rule",
  risk: "Risk decision",
  human: "Human judgment",
  limitation: "Limitation",
  unavailable: "Unavailable",
};

export default function EvidenceChainTag({ kind, label }: { kind: ChainKind; label?: string }) {
  return <span className={`chain-tag chain-tag-${kind}`}>{label ?? LABELS[kind]}</span>;
}
