/**
 * Evidence Dossier — progressive-disclosure detail behind a dimension card.
 * Every field here is either REAL (from ProbeEvidenceRead) or explicitly
 * rendered as Unavailable/Not collected/Not applicable — never invented
 * (no fabricated hashes, timestamps, or telemetry).
 *
 * The opening chain (steps 1-6) tags each statement with EvidenceChainTag —
 * the same taxonomy ReportTraceabilityPanel uses on the Report page — so a
 * reader on the primary Evaluation Detail page, without navigating to the
 * Report, can already tell observed evidence apart from a derived metric, a
 * gate/rule, a risk decision, human judgment, and a limitation. Nothing here
 * is recomputed: every tagged value is a direct read of the same
 * ProbeEvidenceRead fields already rendered below (model identity, dataset
 * identity, raw evidence) — the tags label existing data, they do not add a
 * second copy of it.
 */
import type { ReactNode } from "react";

import type { FriesDimension, ProbeEvidenceRead } from "../api/types";
import ChainStep from "./ChainStep";
import EvidenceChainTag from "./EvidenceChainTag";
import StatusPill from "./StatusPill";

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="kv" style={{ gridTemplateColumns: "180px 1fr", marginBottom: "0.3rem" }}>
      <dt>{label}</dt>
      <dd>{value ?? <span className="unavailable-value">Unavailable</span>}</dd>
    </div>
  );
}

export default function EvidenceDossier({
  dimension,
  probe,
  id,
}: {
  dimension: FriesDimension;
  probe: ProbeEvidenceRead | undefined;
  id?: string;
}) {
  if (!probe) {
    return (
      <details className="dossier-section" id={id}>
        <summary>{dimension.charAt(0) + dimension.slice(1).toLowerCase()}</summary>
        <div className="dossier-section-body">
          <ChainStep>
            <EvidenceChainTag kind="unavailable" />
            <div className="chain-step-body">Not run for this evaluation.</div>
          </ChainStep>
        </div>
      </details>
    );
  }

  const ref = probe.evidence_refs?.[0] as Record<string, unknown> | undefined;
  const documentationSource = probe.metric_values?.documentation_source as
    | Record<string, unknown>
    | null
    | undefined;
  const isUserDataset = probe.evaluation_class === "user_dataset";
  const datasetFilename = isUserDataset ? probe.metric_values?.dataset_filename : null;
  const datasetFingerprint = isUserDataset ? probe.metric_values?.dataset_content_hash : null;
  const groupColumn = isUserDataset ? probe.metric_values?.group_column : null;
  const targetColumn = isUserDataset ? probe.metric_values?.target_column : null;
  const observedGroups = isUserDataset
    ? (probe.metric_values?.observed_groups as { value: string; count: number }[] | undefined)
    : undefined;

  return (
    <details className="dossier-section" id={id}>
      <summary>
        {dimension.charAt(0) + dimension.slice(1).toLowerCase()}
        <StatusPill status={probe.status} />
      </summary>
      <div className="dossier-section-body">
        {/* Step 1: what was observed */}
        <ChainStep>
          <EvidenceChainTag kind="evidence" />
          <div className="chain-step-body">
            <strong>What was evaluated:</strong>{" "}
            {isUserDataset
              ? `Your local dataset (${String(datasetFilename ?? "unnamed file")})`
              : (probe.dataset_key ?? "No dataset — documentation/governance checks only")}
            {probe.evaluation_class ? (
              <>
                {" "}
                — evaluated as {probe.evaluation_class.replaceAll("_", " ")}
                {probe.methodology_version ? ` (methodology ${probe.methodology_version})` : ""}
              </>
            ) : null}
          </div>
        </ChainStep>

        {/* Step 2: derived metric — confidence is the one number this
            dossier computes itself off; every other measured number stays
            in the dimension card above (same figures, not copied here). */}
        <ChainStep>
          <EvidenceChainTag kind="metric" />
          <div className="chain-step-body">
            <strong>Evidence strength:</strong>{" "}
            {probe.confidence != null ? (
              probe.confidence.toFixed(2)
            ) : (
              <EvidenceChainTag kind="unavailable" label="Unavailable" />
            )}
            {" "}— see the dimension card above for the full measured metrics behind this
            score (not repeated here).
          </div>
        </ChainStep>

        {/* Step 3: gate / rule — the same list also used in "Raw / technical
            evidence" below is shown once, here, not duplicated. */}
        <ChainStep>
          <EvidenceChainTag kind="gate" />
          <div className="chain-step-body">
            <strong>Gate / rule:</strong>{" "}
            {probe.gates && probe.gates.length > 0 ? (
              probe.gates.join(", ")
            ) : (
              <span className="muted">No gate failures recorded for this run</span>
            )}
          </div>
        </ChainStep>

        {/* Step 4: risk decision / conclusion */}
        <ChainStep>
          <EvidenceChainTag kind="risk" />
          <div className="chain-step-body">
            <strong>Conclusion:</strong>{" "}
            {probe.aspect_scoring ? (
              probe.aspect_scoring.replaceAll("_", " ")
            ) : (
              <EvidenceChainTag kind="unavailable" label="Not scored" />
            )}
            {probe.scored_risk_id ? (
              <>
                {" "}
                — named risk <span className="mono">{probe.scored_risk_id}</span>
              </>
            ) : probe.risks_triggered && probe.risks_triggered.length > 0 ? (
              <> — risks: {probe.risks_triggered.join(", ")}</>
            ) : null}
            {probe.status_reason ? <div className="field-hint">{probe.status_reason}</div> : null}
          </div>
        </ChainStep>

        {/* Step 5: human judgment — a pointer only; O/S/D is entered and
            stored separately from probe evidence (never invented here, and
            never a second copy of the O/S/D review section on this page). */}
        <ChainStep>
          <EvidenceChainTag kind="human" />
          <div className="chain-step-body">
            Human O/S/D for this dimension is entered separately from this probe's
            evidence — see the O/S/D review section on this page. TrustLens never infers
            O, S, or D from the measurements above.
          </div>
        </ChainStep>

        {/* Step 6: limitations */}
        <ChainStep>
          <EvidenceChainTag kind="limitation" />
          <div className="chain-step-body">
            {probe.limitations?.length ? probe.limitations.join("; ") : "None recorded"}
          </div>
        </ChainStep>

        <h3 style={{ fontSize: "0.9rem", marginTop: "1rem" }}>
          <span className="dossier-step-num">7</span>Model identity
        </h3>
        <Field label="Model ref" value={probe.model_ref} />
        <Field label="Model revision" value={probe.model_revision ? <span className="mono">{probe.model_revision}</span> : null} />

        {(dimension === "EXPLAINABILITY" || dimension === "SAFETY") && (
          <>
            <h3 style={{ fontSize: "0.9rem", marginTop: "1rem" }}>Documentation evidence source</h3>
            {documentationSource ? (
              <>
                <Field
                  label="Source"
                  value={String(documentationSource.documentation_source_type ?? "model_card")}
                />
                <Field
                  label="Pinned revision"
                  value={
                    documentationSource.documentation_revision ? (
                      <span className="mono">{String(documentationSource.documentation_revision)}</span>
                    ) : null
                  }
                />
                <Field
                  label="Content hash"
                  value={
                    documentationSource.documentation_content_hash ? (
                      <span className="mono">{String(documentationSource.documentation_content_hash)}</span>
                    ) : null
                  }
                />
                <Field label="Retrieval status" value={String(documentationSource.retrieval_status ?? "")} />
                {documentationSource.retrieval_error ? (
                  <Field label="Retrieval error" value={String(documentationSource.retrieval_error)} />
                ) : null}
                <Field
                  label="Source URL"
                  value={
                    documentationSource.documentation_url ? (
                      <a
                        href={String(documentationSource.documentation_url)}
                        target="_blank"
                        rel="noreferrer"
                        className="mono"
                      >
                        {String(documentationSource.documentation_url)}
                      </a>
                    ) : null
                  }
                />
              </>
            ) : (
              <p className="field-hint">
                No pinned-revision documentation evidence recorded for this model (not imported
                from Hugging Face, or the card fetch failed).
              </p>
            )}
          </>
        )}

        <h3 style={{ fontSize: "0.9rem", marginTop: "1rem" }}>
          <span className="dossier-step-num">8</span>Dataset identity
        </h3>
        {isUserDataset ? (
          <>
            <Field
              label="Local dataset"
              value={
                <>
                  User-defined — not an approved/certified benchmark
                  {datasetFilename ? ` (${String(datasetFilename)})` : ""}
                </>
              }
            />
            <Field
              label="Dataset fingerprint"
              value={
                datasetFingerprint ? <span className="mono">{String(datasetFingerprint)}</span> : null
              }
            />
            <Field label="Target column" value={targetColumn ? String(targetColumn) : null} />
            <Field label="Group attribute" value={groupColumn ? String(groupColumn) : null} />
            <Field
              label="Groups (rows)"
              value={
                observedGroups?.length
                  ? observedGroups.map((g) => `${g.value} (${g.count})`).join(", ")
                  : null
              }
            />
          </>
        ) : (
          <>
            <Field label="Dataset key" value={probe.dataset_key} />
            <Field label="Dataset revision" value={probe.dataset_revision ? <span className="mono">{probe.dataset_revision}</span> : null} />
          </>
        )}

        <h3 style={{ fontSize: "0.9rem", marginTop: "1rem" }}>
          <span className="dossier-step-num">9</span>Execution / inference
        </h3>
        <Field
          label="Local inference executed"
          value={
            probe.inference_executed == null
              ? "Not applicable"
              : probe.inference_executed
                ? "Yes — local model weights"
                : "No"
          }
        />

        <h3 style={{ fontSize: "0.9rem", marginTop: "1rem" }}>
          <span className="dossier-step-num">10</span>Raw / technical evidence
        </h3>
        <Field label="Evidence hash" value={ref?.hash ? <span className="mono">{String(ref.hash)}</span> : null} />
        <Field label="Evidence URI" value={ref?.uri ? <span className="mono">{String(ref.uri)}</span> : null} />
        {/* Gates already shown, tagged, in the chain above — not repeated here. */}
        {probe.metric_values ? (
          <details style={{ marginTop: "0.5rem" }}>
            <summary style={{ cursor: "pointer", fontSize: "0.82rem", color: "var(--muted)" }}>
              Full persisted metric values (JSON)
            </summary>
            <pre className="json-view">{JSON.stringify(probe.metric_values, null, 2)}</pre>
          </details>
        ) : null}

        <h3 style={{ fontSize: "0.9rem", marginTop: "1rem" }}>
          <span className="dossier-step-num">11</span>Reproducibility
        </h3>
        <p className="field-hint">
          Re-running this exact evaluation contract (same model revision, same dataset revision)
          uses the same local inference path. Per-batch timing is not currently recorded. The
          actual execution device (CPU/GPU) used when a probe ran local inference is recorded
          per-evaluation — see the Context section above.
        </p>
      </div>
    </details>
  );
}
