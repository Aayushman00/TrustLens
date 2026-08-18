import { Navigate, useLocation } from "react-router-dom";

import Layout from "../components/Layout";
import Spinner from "../components/Spinner";
import { useAuth } from "./AuthContext";

/** Wraps all protected routes: restores the session, else redirects to /login. */
export default function RequireAuth() {
  const { user, initializing } = useAuth();
  const location = useLocation();

  if (initializing) {
    return (
      <div className="page-center">
        <Spinner label="Restoring session…" />
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Layout />;
}
