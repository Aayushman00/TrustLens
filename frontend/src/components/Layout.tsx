import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { API_BASE } from "../api/client";

type Health = "checking" | "ok" | "down";

export default function Layout() {
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
