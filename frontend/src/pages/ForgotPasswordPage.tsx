import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

/**
 * TrustLens does not currently expose a password-reset endpoint. This page
 * collects the email for the user's own reference and is honest that it
 * cannot submit anywhere real, rather than faking a "check your email" flow.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setAcknowledged(true);
  }

  return (
    <div className="page-center">
      <div className="card login-card">
        <h1 className="brand-title">Forgot password</h1>
        <p className="muted">
          Self-service password reset isn't available in this TrustLens deployment yet.
        </p>
        {!acknowledged ? (
          <form className="form" onSubmit={handleSubmit}>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="researcher@trustlens.local"
              />
            </label>
            <button type="submit" className="btn" disabled={!email.trim()}>
              Continue
            </button>
          </form>
        ) : (
          <div className="auth-shell-note">
            Password resets are handled by your TrustLens administrator. Contact them and
            reference the account email <strong>{email}</strong> — there is no automated reset
            email from this instance.
          </div>
        )}
        <p className="link-row">
          <Link to="/login">Back to sign in</Link>
        </p>
      </div>
    </div>
  );
}
