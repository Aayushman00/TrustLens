import { API_BASE } from "../api/client";

export default function SettingsPage() {
  return (
    <>
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p className="muted">Local engine information.</p>
        </div>
      </div>

      <div className="card">
        <h2>TrustLens Local Engine</h2>
        <p className="muted">
          Evaluations, model storage and evidence all run on this machine.
        </p>
        <details>
          <summary style={{ cursor: "pointer", fontWeight: 600 }}>Technical details</summary>
          <dl className="kv" style={{ marginTop: "0.8rem" }}>
            <dt>Local API</dt>
            <dd className="mono">{API_BASE}</dd>
            <dt>Backend</dt>
            <dd>FastAPI + PostgreSQL + Celery worker</dd>
            <dt>Evidence storage</dt>
            <dd>Local object storage (MinIO)</dd>
          </dl>
        </details>
      </div>
    </>
  );
}
