import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, matchPath, NavLink, Outlet, useLocation } from "react-router-dom";

import { API_BASE } from "../api/client";
import "../ds/tokens.css";
import "../ds/ds.css";
import "./Layout.css";

type Health = "checking" | "ok" | "down";

const HEALTH_TEXT: Record<Health, string> = {
  checking: "checking…",
  ok: "connected",
  down: "unreachable",
};

// One entry per real route in App.tsx; specific patterns before parameterised ones.
const ROUTE_TITLES: [pattern: string, title: string][] = [
  ["/", "Overview"],
  ["/models/import", "Import model"],
  ["/models/:id", "Model"],
  ["/models", "Models"],
  ["/evaluations/new", "New evaluation"],
  ["/evaluations/:id/review", "Review"],
  ["/evaluations/:id", "Evaluation"],
  ["/evaluations", "Evaluations"],
  ["/reports/:evaluationId", "Report"],
  ["/documentation", "Documentation"],
  ["/settings", "Settings"],
];

export function routeTitle(pathname: string): string | null {
  const hit = ROUTE_TITLES.find(([pattern]) => matchPath({ path: pattern, end: true }, pathname));
  return hit ? hit[1] : null;
}

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="tl-shell-icon"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

const NAV_GROUPS: {
  label: string;
  items: { to: string; label: string; end?: boolean; icon: ReactNode }[];
}[] = [
  {
    label: "Workspace",
    items: [
      { to: "/", label: "Overview", end: true, icon: <path d="M3 11l9-8 9 8M5 10v10h14V10" /> },
      {
        to: "/models",
        label: "Models",
        icon: <path d="M12 3l9 5v8l-9 5-9-5V8l9-5zM3 8l9 5 9-5M12 13v8" />,
      },
      {
        to: "/evaluations",
        label: "Evaluations",
        icon: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
      },
    ],
  },
  {
    label: "System",
    items: [
      {
        to: "/documentation",
        label: "Documentation",
        icon: <path d="M4 5a2 2 0 012-2h13v18H6a2 2 0 01-2-2V5zM4 19a2 2 0 012-2h13" />,
      },
      {
        to: "/settings",
        label: "Settings",
        icon: (
          <>
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
          </>
        ),
      },
    ],
  },
];

function useShellTheme(): "dark" | "light" {
  const read = (): "dark" | "light" => {
    const forced = document.documentElement.dataset.theme;
    if (forced === "light" || forced === "dark") return forced;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  };
  const [theme, setTheme] = useState(read);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = () => setTheme(read());
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return theme;
}

export default function Layout() {
  const [health, setHealth] = useState<Health>("checking");
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const theme = useShellTheme();
  const mainRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const lastPath = useRef(pathname);

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

  // Page title follows the route; unknown paths keep the document default.
  useEffect(() => {
    const title = routeTitle(pathname);
    if (title) document.title = `${title} · TrustLens`;
  }, [pathname]);

  // After a client-side navigation, move focus to <main> so keyboard and
  // screen-reader users land on the new page, not on the link they used.
  useEffect(() => {
    setMenuOpen(false);
    if (lastPath.current !== pathname) {
      lastPath.current = pathname;
      mainRef.current?.focus({ preventScroll: true });
    }
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className="app-shell">
      <a href="#main-content" className="tl tl-shell-skip" data-theme={theme}>
        Skip to content
      </a>
      <header className="tl tl-shell" data-theme={theme}>
        <div className="tl-shell-top">
          <Link to="/" className="tl-shell-brand" aria-label="TrustLens, go to overview">
            <span className="tl-shell-mark" aria-hidden="true">
              TL
            </span>
            <span className="tl-display">TrustLens</span>
          </Link>
          <button
            type="button"
            ref={menuButtonRef}
            className="tl-shell-menu"
            aria-expanded={menuOpen}
            aria-controls="primary-nav"
            onClick={() => setMenuOpen((o) => !o)}
          >
            <Icon>{menuOpen ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}</Icon>
            <span>{menuOpen ? "Close menu" : "Menu"}</span>
          </button>
        </div>

        <div className="tl-shell-panel" id="primary-nav" data-open={menuOpen}>
          <p className="tl-shell-engine" title="Evaluations run on this machine — no model upload">
            <span className="tl-shell-engine-dot" aria-hidden="true" />
            Local engine
          </p>

          <nav aria-label="Primary">
            {NAV_GROUPS.map((group) => (
              <div key={group.label} className="tl-shell-group">
                <p className="tl-shell-label" id={`nav-${group.label}`}>
                  {group.label}
                </p>
                <ul aria-labelledby={`nav-${group.label}`}>
                  {group.items.map((item) => (
                    <li key={item.to}>
                      <NavLink to={item.to} end={item.end}>
                        <Icon>{item.icon}</Icon>
                        {item.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>

          <p className="tl-shell-health" role="status" data-health={health}>
            <span className="tl-shell-health-mark" aria-hidden="true" />
            Local API: {HEALTH_TEXT[health]}
          </p>
        </div>
      </header>
      <main className="app-main" id="main-content" ref={mainRef} tabIndex={-1}>
        <div className="container">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
