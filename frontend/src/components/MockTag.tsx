/**
 * Placeholder-data contract (see frontend/src/mocks/README): any value that
 * did not come from a real API response must be visibly marked so it is
 * never mistaken for a measurement. Use inline on a value, or MockBanner for
 * a whole section.
 */
import type { ReactNode } from "react";

export default function MockTag({ label = "Demo data" }: { label?: string }) {
  return <span className="mock-tag">{label}</span>;
}

export function MockBanner({ children }: { children: ReactNode }) {
  return (
    <div className="mock-banner">
      <MockTag />
      <span>{children}</span>
    </div>
  );
}
