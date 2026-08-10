import { useEffect, useState } from "react";

type HealthState = "checking" | "connected" | "unavailable";

export default function App() {
  const [health, setHealth] = useState<HealthState>("checking");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const res = await fetch("http://localhost:8000/health");
        if (!res.ok) throw new Error("bad status");
        const data = (await res.json()) as { status?: string };
        if (!cancelled) {
          setHealth(data.status === "ok" ? "connected" : "unavailable");
        }
      } catch {
        if (!cancelled) setHealth("unavailable");
      }
    }

    void check();
    return () => {
      cancelled = true;
    };
  }, []);

  const healthLabel =
    health === "checking"
      ? "Backend: Checking…"
      : health === "connected"
        ? "Backend: Connected"
        : "Backend: Unavailable";

  return (
    <main className="page">
      <h1>TrustLens</h1>
      <p className="tagline">Trustworthy ML Benchmarking Platform</p>
      <p className="phase">Phase 1 — Repository Bootstrap</p>
      <p className={`health health-${health}`}>{healthLabel}</p>
    </main>
  );
}
