import { HashBadge } from "./HashBadge";

export interface EvidenceRef {
  evidence_id: string | null;
  hash: string | null;
  uri: string | null;
  content_type: string | null;
  probe_name: string | null;
  created_at: string | null;
}

const str = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);

/** evidence_refs are Record<string, unknown> on the wire — narrow them here. */
export function toEvidenceRef(raw: Record<string, unknown>): EvidenceRef {
  return {
    evidence_id: str(raw.evidence_id),
    hash: str(raw.hash),
    uri: str(raw.uri),
    content_type: str(raw.content_type),
    probe_name: str(raw.probe_name),
    created_at: str(raw.created_at),
  };
}

export function EvidenceChip({ evidence, onTrace }: { evidence: EvidenceRef; onTrace?: (e: EvidenceRef) => void }) {
  const id = evidence.evidence_id ? `ev_${evidence.evidence_id.slice(0, 8)}` : "ev_unknown";
  const body = (
    <>
      <span className="tl-evchip__id">{id}</span>
      <span className="tl-evchip__type">{evidence.content_type ?? "unknown type"}</span>
    </>
  );
  return (
    <span className="tl-evchip">
      {onTrace ? (
        <button
          type="button"
          className="tl-evchip__main"
          onClick={() => onTrace(evidence)}
          aria-label={`Trace evidence ${evidence.evidence_id ?? "unknown"}`}
        >
          {body}
        </button>
      ) : (
        <span className="tl-evchip__main">{body}</span>
      )}
      <HashBadge hash={evidence.hash} label={`${id} hash`} />
    </span>
  );
}
