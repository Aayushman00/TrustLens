import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import ErrorNotice from "../components/ErrorNotice";
import { useAuth } from "../auth/AuthContext";

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? "/";

  if (user) return <Navigate to={from} replace />;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-center">
      <div className="card login-card">
        <h1 className="brand-title">TrustLens</h1>
        <p className="muted">Trustworthy ML benchmarking — sign in to continue.</p>
        <form onSubmit={handleSubmit} className="form">
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="researcher@trustlens.local"
              autoComplete="username"
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <ErrorNotice error={error} />
          <button type="submit" className="btn" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <details className="seed-hint">
          <summary>Dev seed users</summary>
          <ul>
            <li>
              <code>researcher@trustlens.local</code> / <code>trustlens-researcher-dev</code>
            </li>
            <li>
              <code>reviewer@trustlens.local</code> / <code>trustlens-reviewer-dev</code>
            </li>
            <li>
              <code>admin@trustlens.local</code> / <code>trustlens-admin-dev</code>
            </li>
          </ul>
        </details>
      </div>
    </div>
  );
}
