import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { API_BASE } from "../api/client";
import { useAuth } from "../auth/AuthContext";

type Health = "checking" | "ok" | "down";

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [health, setHealth] = useState<Health>("checking");

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const res = await fetch(`${API_BASE}/health`);
        if (!cancelled) setHealth(res.ok ? "ok" : "down");
      } catch {
        if (!cancelled) setHealth("down");
      }
    }
    void check();
    const timer = setInterval(check, 30_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand">
            TrustLens
          </NavLink>
          <nav className="nav-links">
            <NavLink to="/" end>
              Dashboard
            </NavLink>
            <NavLink to="/models">Models</NavLink>
            <NavLink to="/leaderboard">Leaderboard</NavLink>
          </nav>
          <div className="topbar-right">
            <span className={`health-dot health-${health}`} title={`API: ${health}`} />
            {user ? (
              <>
                <span className="user-email">{user.email}</span>
                <span className={`badge role-${user.role}`}>{user.role}</span>
                <button type="button" className="btn btn-ghost" onClick={handleLogout}>
                  Log out
                </button>
              </>
            ) : null}
          </div>
        </div>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </div>
  );
}
