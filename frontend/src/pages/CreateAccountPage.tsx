import { Link } from "react-router-dom";

/**
 * TrustLens does not currently expose a self-service account-creation
 * endpoint (only login/refresh/me exist). Rather than fake a submission,
 * this page is an honest, polished dead-end that tells the user how
 * accounts are actually provisioned today.
 */
export default function CreateAccountPage() {
  return (
    <div className="page-center">
      <div className="card login-card">
        <h1 className="brand-title">Create account</h1>
        <p className="muted">
          Self-service account creation isn't available in this TrustLens deployment yet.
        </p>
        <div className="auth-shell-note">
          New researcher accounts are provisioned by your TrustLens administrator directly on
          this instance. Once created, you'll receive normal researcher access — administrator
          access is never selectable at sign-up.
        </div>
        <p className="link-row">
          <Link to="/login">Back to sign in</Link>
        </p>
      </div>
    </div>
  );
}
