import { API_BASE } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function SettingsPage() {
  const { user } = useAuth();

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p className="muted">Account and local engine information.</p>
        </div>
      </div>

      <div className="card">
        <h2>Account</h2>
        <dl className="kv">
          <dt>Email</dt>
          <dd>{user?.email ?? "—"}</dd>
          <dt>Role</dt>
          <dd>
            <span className={`badge role-${user?.role ?? "researcher"}`}>{user?.role ?? "—"}</span>
          </dd>
        </dl>
        <p className="field-hint">
          Roles are assigned by a TrustLens administrator and cannot be changed here.
          Admin-only evaluation options (such as the proxy evaluation) are shown or hidden
          automatically based on this role.
        </p>
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
