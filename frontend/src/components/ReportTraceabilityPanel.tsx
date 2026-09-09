/**
 * Evidence Traceability — the interactive "Why?" drill-down for the Report
 * page. One panel per FRIES dimension, walking the actual chain:
 *
 *   conclusion -> risk/status -> gate/rule -> [metric, in the dimension
 *   card above] -> evidence references -> human O/S/D -> FRIES dimension
 *   score
 *
 * Every value rendered here is a direct read of ReportTraceabilityEntry —
 * already assembled server-side from ProbeEvidenceRead/final_scores. This
 * component only presents the chain; it never computes, combines, or
 * re-derives any number.
 */
import type { FriesDimension, ReportTraceabilityEntry } from "../api/types";
import { fmtOsd } from "../lib/format";
import Row from "./ChainStep";
import EvidenceChainTag from "./EvidenceChainTag";
import StatusPill from "./StatusPill";

const DIMENSION_LABEL: Record<FriesDimension, string> = {
  FAIRNESS: "Fairness",
  ROBUSTNESS: "Robustness",
  INTEGRITY: "Integrity",
  EXPLAINABILITY: "Explainability",
  SAFETY: "Safety",
};

export default function ReportTraceabilityPanel({ entry }: { entry: ReportTraceabilityEntry }) {
  const label = DIMENSION_LABEL[entry.dimension];
  const isDocProbe = entry.dimension === "EXPLAINABILITY" || entry.dimension === "SAFETY";

  return (
    <details className="dossier-section">
      <summary>
        {label}
        <StatusPill status={entry.status} />
      </summary>
      <div className="dossier-section-body">
        {/* Step 1: conclusion / risk-status classification */}
        <Row>
          <EvidenceChainTag kind="risk" />
          <div className="chain-step-body">
            <strong>Conclusion:</strong>{" "}
            {entry.aspect_scoring ? entry.aspect_scoring.replaceAll("_", " ") : "Not scored"}
            {entry.scored_risk_id ? (
              <>
                {" "}
                — named risk <span className="mono">{entry.scored_risk_id}</span>
              </>
            ) : entry.risks_triggered && entry.risks_triggered.length > 0 ? (
              <> — risks: {entry.risks_triggered.join(", ")}</>
            ) : (
              " — no material risk qualified from this evidence"
            )}
            {entry.status_reason ? <div className="field-hint">{entry.status_reason}</div> : null}
          </div>
        </Row>

        {/* Step 2: gate/rule */}
        <Row>
          <EvidenceChainTag kind="gate" />
          <div className="chain-step-body">
            <strong>Gate / rule:</strong>{" "}
            {entry.gates && entry.gates.length > 0 ? (
              <span>{entry.gates.join(", ")}</span>
            ) : (
              <span className="muted">No gate failures recorded for this run</span>
            )}
          </div>
        </Row>

        {/* Step 3: metric — pointer only, never duplicated here */}
        <Row>
          <EvidenceChainTag kind="metric" />
          <div className="chain-step-body">
            <strong>Metric:</strong>{" "}
            {isDocProbe ? (
              <>
                Documentation coverage ={" "}
                {typeof entry.coverage_ratio === "number" ? entry.coverage_ratio.toFixed(2) : "unavailable"}
                {" "}— see the {label} card above for section-by-section detail. Never an
                "{label} score".
              </>
            ) : (
              <>The measured numbers behind this conclusion are in the {label} card above (same data — not repeated here to avoid a second copy of the same measurement).</>
            )}
          </div>
        </Row>

        {/* Step 4: evidence references */}
        <Row>
          <EvidenceChainTag kind="evidence" />
          <div className="chain-step-body">
            <strong>Evidence:</strong>{" "}
            {entry.evidence_refs.length > 0 ? (
              entry.evidence_refs.map((ref, i) => {
                const r = ref as Record<string, unknown>;
                return (
                  <div key={i} className="mono" style={{ fontSize: "0.82rem" }}>
                    {typeof r.hash === "string" ? r.hash : "no hash"}
                    {typeof r.uri === "string" ? ` · ${r.uri}` : ""}
                  </div>
                );
              })
            ) : (
              <span className="muted">No evidence artifact recorded</span>
            )}
          </div>
        </Row>

        {/* Step 5: human O/S/D */}
        <Row>
          <EvidenceChainTag kind="human" />
          <div className="chain-step-body">
            <strong>Human O/S/D:</strong>{" "}
            {entry.human_osd ? (
              <>
                O={fmtOsd(entry.human_osd.O)} · S={fmtOsd(entry.human_osd.S)} · D=
                {fmtOsd(entry.human_osd.D)}
                {entry.human_osd.O_source || entry.human_osd.S_source || entry.human_osd.D_source ? (
                  <span className="muted">
                    {" "}
                    (source:{" "}
                    {[entry.human_osd.O_source, entry.human_osd.S_source, entry.human_osd.D_source]
                      .filter(Boolean)
                      .join(", ") || "unavailable"}
                    )
                  </span>
                ) : null}
              </>
            ) : (
              <EvidenceChainTag kind="unavailable" label="Not settled — O/S/D incomplete for this aspect" />
            )}
          </div>
        </Row>

        {/* Step 6: FRIES dimension score */}
        <Row>
          <EvidenceChainTag kind="metric" />
          <div className="chain-step-body">
            <strong>FRIES dimension score:</strong>{" "}
            {typeof entry.fries_dimension_score === "number" ? (
              entry.fries_dimension_score.toFixed(3)
            ) : (
              <EvidenceChainTag kind="unavailable" label="Withheld" />
            )}
          </div>
        </Row>

        {/* Limitations */}
        {entry.limitations && entry.limitations.length > 0 ? (
          <Row>
            <EvidenceChainTag kind="limitation" />
            <div className="chain-step-body">{entry.limitations.join("; ")}</div>
          </Row>
        ) : null}
      </div>
    </details>
  );
}
