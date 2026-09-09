/**
 * Full evaluation report — Phase 6.
 *
 * Every section here renders a value already computed and persisted by the
 * backend report builder (backend/app/reports/builder.py). This page never
 * recomputes a metric, a gate, a risk decision, an O/S/D value, or a FRIES
 * score — it only presents them, with an explicit visual distinction
 * between observed evidence, derived metrics, gates/rules, risk decisions,
 * human judgment, limitations, and unavailable/withheld information (see
 * EvidenceChainTag).
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, apiFetch } from "../api/client";
import { FRIES_DIMENSIONS, type FriesDimension, type ReportRead } from "../api/types";
import DimensionCard from "../components/DimensionCard";
import ErrorNotice from "../components/ErrorNotice";
import EvidenceChainTag from "../components/EvidenceChainTag";
import ModeDisclosureBanner from "../components/ModeDisclosure";
import ReportTraceabilityPanel from "../components/ReportTraceabilityPanel";
import ScoreBars from "../components/ScoreBars";
import Spinner from "../components/Spinner";
import { traceabilityEntryToProbeEvidence } from "../lib/report";
import { fmtDateTime, fmtOsd } from "../lib/format";

const DIMENSION_LABEL: Record<FriesDimension, string> = {
  FAIRNESS: "Fairness",
  ROBUSTNESS: "Robustness",
  INTEGRITY: "Integrity",
  EXPLAINABILITY: "Explainability",
  SAFETY: "Safety",
};

export default function ReportPage() {
  const { evaluationId } = useParams();
  const [report, setReport] = useState<ReportRead | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const row = await apiFetch<ReportRead>(`/v1/reports/${evaluationId}`);
        if (!cancelled) setReport(row);
      } catch (err) {
        if (!cancelled) setError(err);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [evaluationId]);

  function downloadJson() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report.report_json, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `trustlens-report-${report.evaluation_id.slice(0, 8)}-v${report.version}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function regenerate() {
    setRegenerating(true);
    setError(null);
    try {
      setReport(
        await apiFetch<ReportRead>(`/v1/reports/${evaluationId}/generate`, {
          method: "POST",
        }),
      );
    } catch (err) {
      setError(err);
    } finally {
      setRegenerating(false);
    }
  }

  if (error != null && report == null) {
    if (error instanceof ApiError && error.code === "NOT_FINALIZED") {
      return (
        <div className="notice notice-info">
          Reports are available only after the evaluation reaches FINALIZED.{" "}
          <Link to={`/evaluations/${evaluationId}`}>Back to the evaluation</Link>.
        </div>
      );
    }
    return <ErrorNotice error={error} />;
  }
  if (report == null) {
    return <Spinner label="Fetching report (generates on first request)…" />;
  }

  const doc = report.report_json;
  const score = doc.score;
  const withheld = score.scoring_withheld || score.fries_score == null;
  const probesByDim = new Map(doc.probes.map((p) => [p.dimension, p]));
  const traceabilityByDim = new Map(doc.evidence_traceability.map((e) => [e.dimension, e]));
  const finalizedAspects = (doc.score.finalized_osd?.aspects as
    | { aspect: string; O: number | null; S: number | null; D: number | null; O_source?: string | null; S_source?: string | null; D_source?: string | null }[]
    | undefined) ?? [];
  const exec = doc.execution_environment;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Report v{report.version}</h1>
          <p className="muted">
            <Link to={`/evaluations/${report.evaluation_id}`} className="mono">
              Evaluation {report.evaluation_id.slice(0, 8)}…
            </Link>{" "}
            · generated {fmtDateTime(report.generated_at)}
          </p>
        </div>
        <div className="btn-row">
          <button type="button" className="btn" onClick={downloadJson}>
            Download JSON
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={regenerating}
            onClick={() => void regenerate()}
          >
            {regenerating ? "Regenerating…" : "Regenerate"}
          </button>
        </div>
      </div>

      <ModeDisclosureBanner disclosure={report.mode_disclosure} />
      <ErrorNotice error={error} />

      {/* 1. Executive Assessment */}
      <div className="card">
        <h2>Executive Assessment</h2>
        {withheld ? (
          <div className="notice notice-info">
            <strong>FRIES withheld.</strong> {doc.executive_summary.headline}
            <p className="field-hint" style={{ marginTop: "0.4rem" }}>
              {score.note}
            </p>
          </div>
        ) : (
          <>
            <div className="fries-hero">
              <span className="fries-value">{score.fries_score!.toFixed(2)}</span>
              <span className="fries-label">original FRIES (0–10)</span>
            </div>
            <p className="muted">{score.note}</p>
          </>
        )}
        <p style={{ marginTop: withheld ? 0 : "0.6rem" }}>{doc.executive_summary.headline}</p>
        {doc.executive_summary.bullets.length > 0 ? (
          <ul>
            {doc.executive_summary.bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
        ) : null}
      </div>

      {/* 2. Evaluation Contract */}
      <div className="card">
        <h2>Evaluation Contract</h2>
        <dl className="kv">
          <dt>Contract kind</dt>
          <dd>{String(doc.reproducibility.contract_kind ?? "documentation_only")}</dd>
          <dt>Task</dt>
          <dd>{String(doc.evaluation.finalized_context.task ?? "—")}</dd>
          <dt>Dataset (comparability label)</dt>
          <dd>{String(doc.evaluation.finalized_context.dataset ?? "—")}</dd>
          <dt>Config</dt>
          <dd>{String(doc.evaluation.finalized_context.config ?? "—")}</dd>
          <dt>Pairing ID</dt>
          <dd className="mono">{String(doc.reproducibility.pairing_id ?? "—")}</dd>
        </dl>
      </div>

      {/* 3. Model Identity */}
      <div className="card">
        <h2>Model Identity</h2>
        <dl className="kv">
          <dt>Model reference</dt>
          <dd>
            <Link to={`/models/${doc.evaluation.model_id}`}>{doc.evaluation.model_ref}</Link>
          </dd>
          <dt>Frozen revision</dt>
          <dd className="mono">{String(doc.reproducibility.model_revision ?? "unpinned")}</dd>
        </dl>
      </div>

      {/* 4. Dataset Identity */}
      <div className="card">
        <h2>Dataset Identity</h2>
        <dl className="kv">
          <dt>Dataset key</dt>
          <dd>{String(doc.reproducibility.dataset_key ?? "—")}</dd>
          <dt>Dataset revision</dt>
          <dd className="mono">{String(doc.reproducibility.dataset_revision ?? "—")}</dd>
          <dt>User dataset ID</dt>
          <dd className="mono">{String(doc.reproducibility.user_dataset_id ?? "—")}</dd>
          <dt>Dataset content hash</dt>
          <dd className="mono">{String(doc.reproducibility.dataset_content_hash ?? "—")}</dd>
        </dl>
      </div>

      {/* 5. Local Execution Environment */}
      <div className="card">
        <h2>Local Execution Environment</h2>
        {exec ? (
          <dl className="kv">
            <dt>Execution device</dt>
            <dd>
              {exec.execution_device === "cuda"
                ? `GPU (${exec.gpu_name ?? "CUDA device"})`
                : `${exec.execution_device ?? exec.device ?? "unknown"}${exec.fallback_reason ? ` — ${exec.fallback_reason}` : ""}`}
            </dd>
            <dt>Inference backend</dt>
            <dd>{exec.inference_backend ?? "—"}</dd>
            <dt>CUDA available</dt>
            <dd>{exec.cuda_available == null ? "—" : String(exec.cuda_available)}</dd>
          </dl>
        ) : (
          <p className="empty">
            Not recorded — no probe performed local model inference for this evaluation
            (e.g. a documentation-only contract, or the evaluation predates this field).
          </p>
        )}
      </div>

      {/* 6-10. Fairness / Robustness / Integrity / Explainability / Safety Evidence */}
      <h2>Dimension Evidence</h2>
      <div className="dimension-grid">
        {FRIES_DIMENSIONS.map((dim) => {
          const entry = traceabilityByDim.get(dim);
          const probe = probesByDim.get(dim);
          return (
            <DimensionCard
              key={dim}
              dimension={dim}
              probe={entry ? traceabilityEntryToProbeEvidence(entry, probe) : undefined}
              onViewEvidence={() => {
                document.getElementById(`report-trace-${dim}`)?.setAttribute("open", "true");
                document.getElementById(`report-trace-${dim}`)?.scrollIntoView({ behavior: "smooth" });
              }}
            />
          );
        })}
      </div>

      {/* 11. Evidence Traceability — the interactive "Why?" drill-down */}
      <h2>Evidence Traceability</h2>
      <p className="muted">
        For each dimension: conclusion → risk/status → gate/rule → metric → evidence
        references → human O/S/D → FRIES dimension score. Tags on the left mark whether
        a line is <EvidenceChainTag kind="evidence" />, <EvidenceChainTag kind="metric" />,{" "}
        <EvidenceChainTag kind="gate" />, <EvidenceChainTag kind="risk" />,{" "}
        <EvidenceChainTag kind="human" />, a <EvidenceChainTag kind="limitation" />, or{" "}
        <EvidenceChainTag kind="unavailable" />.
      </p>
      {FRIES_DIMENSIONS.map((dim) => {
        const entry = traceabilityByDim.get(dim);
        if (!entry) {
          return (
            <details className="dossier-section" key={dim} id={`report-trace-${dim}`}>
              <summary>{DIMENSION_LABEL[dim]}</summary>
              <div className="dossier-section-body">
                <p className="empty">No traceability entry recorded for this dimension.</p>
              </div>
            </details>
          );
        }
        return <div id={`report-trace-${dim}`} key={dim}><ReportTraceabilityPanel entry={entry} /></div>;
      })}

      {/* 12. Human O/S/D Assessment */}
      <div className="card">
        <h2>Human O/S/D Assessment</h2>
        {finalizedAspects.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Aspect</th>
                  <th className="num">O</th>
                  <th className="num">S</th>
                  <th className="num">D</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {finalizedAspects.map((a) => (
                  <tr key={a.aspect}>
                    <td>{a.aspect.toLowerCase()}</td>
                    <td className="num">{fmtOsd(a.O)}</td>
                    <td className="num">{fmtOsd(a.S)}</td>
                    <td className="num">{fmtOsd(a.D)}</td>
                    <td className="muted">
                      {[a.O_source, a.S_source, a.D_source].filter(Boolean).join(", ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">
            No settled human O/S/D yet — required aspects are incomplete, which is why FRIES
            is withheld above. O, S, and D are always human-entered; TrustLens never infers
            them from probe evidence.
          </p>
        )}
      </div>

      {/* 13. FRIES Assessment */}
      <div className="card">
        <h2>FRIES Assessment</h2>
        {withheld ? (
          <div className="notice notice-info">
            <strong>Withheld.</strong> FRIES is only computed once every required aspect has a
            complete human O/S/D triple. See Human O/S/D Assessment above for what is missing.
          </div>
        ) : (
          <ScoreBars scores={score.dimension_scores} />
        )}
      </div>

      {/* 14. Reproducibility Information */}
      <div className="card">
        <h2>Reproducibility Information</h2>
        <dl className="kv">
          <dt>Model reference</dt>
          <dd className="mono">{String(doc.reproducibility.model_ref ?? "—")}</dd>
          <dt>Model revision</dt>
          <dd className="mono">{String(doc.reproducibility.model_revision ?? "unpinned")}</dd>
          <dt>TrustLens version</dt>
          <dd>{String(doc.reproducibility.trustlens_version ?? "—")}</dd>
          <dt>Contract kind</dt>
          <dd>{String(doc.reproducibility.contract_kind ?? "documentation_only")}</dd>
        </dl>
        <p className="field-hint">
          Re-running this exact contract (same model + dataset revision) uses the same local
          inference path. This is reproducible configuration, not a claim of bitwise-identical
          output.
        </p>
      </div>

      {/* 15. Limitations */}
      <div className="card">
        <h2>Limitations</h2>
        {doc.limitations.length > 0 ? (
          <ul>
            {doc.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        ) : (
          <p className="empty">No limitations recorded.</p>
        )}
      </div>

      {/* 16. Documentation Sources */}
      <div className="card">
        <h2>Documentation Sources</h2>
        {doc.documentation_sources.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Type</th>
                  <th>URL</th>
                  <th>Revision</th>
                  <th>Hash</th>
                  <th>Retrieval</th>
                </tr>
              </thead>
              <tbody>
                {doc.documentation_sources.map((s) => (
                  <tr key={s.id}>
                    <td>{s.source_kind === "huggingface_hub" ? "HF card (pinned)" : "User-supplied"}</td>
                    <td>{s.documentation_type.replaceAll("_", " ")}</td>
                    <td className="mono" style={{ maxWidth: "16rem", overflowWrap: "break-word" }}>
                      {s.url ? (
                        <a href={s.url} target="_blank" rel="noreferrer">
                          {s.url}
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="mono">{s.documentation_revision ? s.documentation_revision.slice(0, 10) : "—"}</td>
                    <td className="mono">{s.documentation_content_hash ? s.documentation_content_hash.slice(0, 18) + "…" : "—"}</td>
                    <td>{s.retrieval_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">No documentation sources recorded for this model.</p>
        )}
      </div>

      <div className="card">
        <h2>Artifacts</h2>
        <dl className="kv">
          <dt>JSON</dt>
          <dd className="mono">{report.json_uri}</dd>
          <dt>JSON hash</dt>
          <dd className="mono">{report.json_hash}</dd>
          <dt>PDF</dt>
          <dd className="mono">{report.pdf_uri ?? "not generated (PDF disabled on host)"}</dd>
          {report.pdf_hash ? (
            <>
              <dt>PDF hash</dt>
              <dd className="mono">{report.pdf_hash}</dd>
            </>
          ) : null}
        </dl>
        <p className="field-hint">
          URIs point at MinIO object storage (s3://) — use the JSON download above for the
          canonical report; artifacts are fetched server-side, not from the browser.
        </p>
      </div>

      <div className="card">
        <h2>Full report JSON</h2>
        <details>
          <summary>Show report_v1 payload</summary>
          <pre className="json-view">{JSON.stringify(report.report_json, null, 2)}</pre>
        </details>
      </div>
    </>
  );
}
