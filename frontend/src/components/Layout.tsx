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

  const initial = user?.email ? user.email[0]!.toUpperCase() : "?";

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar" aria-label="Primary navigation">
        <NavLink to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            TL
          </span>
          TrustLens
        </NavLink>
        <div className="local-engine-tag" title="Evaluations run on this machine — no model upload">
          <span className="local-engine-dot" aria-hidden="true" />
          Local Engine
        </div>

        <div className="nav-section-label">Workspace</div>
        <nav className="nav-links">
          <NavLink to="/" end>
            <span className="nav-icon" aria-hidden="true">
              ⌂
            </span>
            Overview
          </NavLink>
          <NavLink to="/models">
            <span className="nav-icon" aria-hidden="true">
              ▣
            </span>
            Models
          </NavLink>
          <NavLink to="/evaluations">
            <span className="nav-icon" aria-hidden="true">
              ≣
            </span>
            Evaluations
          </NavLink>
          <NavLink to="/leaderboard">
            <span className="nav-icon" aria-hidden="true">
              ⚑
            </span>
            Leaderboard
          </NavLink>
        </nav>

        <div className="nav-section-label">System</div>
        <nav className="nav-links">
          <NavLink to="/documentation">
            <span className="nav-icon" aria-hidden="true">
              ▤
            </span>
            Documentation
          </NavLink>
          <NavLink to="/settings">
            <span className="nav-icon" aria-hidden="true">
              ⚙
            </span>
            Settings
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <div className="health-row">
            <span className={`health-dot health-${health}`} title={`API: ${health}`} />
            Local API: {health === "ok" ? "connected" : health === "down" ? "unreachable" : "checking…"}
          </div>
          {user ? (
            <>
              <div className="sidebar-user">
                <span className="sidebar-user-avatar" aria-hidden="true">
                  {initial}
                </span>
                <div className="sidebar-user-meta">
                  <div className="sidebar-user-email">{user.email}</div>
                  <span className={`badge role-${user.role}`}>{user.role}</span>
                </div>
              </div>
              <button type="button" className="btn btn-ghost" onClick={handleLogout}>
                Log out
              </button>
            </>
          ) : null}
        </div>
      </aside>
      <main className="app-main">
        <div className="container" id="main-content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
