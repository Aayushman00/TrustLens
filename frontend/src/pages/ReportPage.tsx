import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, apiFetch } from "../api/client";
import type { ReportRead } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import ModeDisclosureBanner from "../components/ModeDisclosure";
import ScoreBars from "../components/ScoreBars";
import Spinner from "../components/Spinner";
import { fmtDateTime } from "../lib/format";

function dimensionScores(report: ReportRead): Record<string, number> | null {
  const score = report.report_json.score;
  if (score && typeof score === "object" && "dimension_scores" in score) {
    const dims = (score as { dimension_scores: unknown }).dimension_scores;
    if (dims && typeof dims === "object") return dims as Record<string, number>;
  }
  return null;
}

function executiveSummary(report: ReportRead): string | null {
  const summary = report.report_json.executive_summary;
  return typeof summary === "string" ? summary : null;
}

function scoreNote(report: ReportRead): string | null {
  const score = report.report_json.score;
  if (score && typeof score === "object" && "note" in score) {
    const note = (score as { note: unknown }).note;
    return typeof note === "string" ? note : null;
  }
  return null;
}

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
          Reports exist only for finalized evaluations — this one is not finalized yet.{" "}
          <Link to={`/evaluations/${evaluationId}`}>Back to the evaluation</Link>.
        </div>
      );
    }
    return <ErrorNotice error={error} />;
  }
  if (report == null) {
    return <Spinner label="Fetching report (generates on first request)…" />;
  }

  const dims = dimensionScores(report);
  const summary = executiveSummary(report);
  const note = scoreNote(report);

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

      <div className="card">
        <h2>Score</h2>
        <div className="fries-hero">
          <span className="fries-value">{report.fries_score.toFixed(2)}</span>
          <span className="fries-label">original FRIES (0–10)</span>
        </div>
        {dims ? <ScoreBars scores={dims} /> : null}
        {note ? <p className="muted">{note}</p> : null}
      </div>

      {summary ? (
        <div className="card">
          <h2>Executive summary</h2>
          <p>{summary}</p>
        </div>
      ) : null}

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
