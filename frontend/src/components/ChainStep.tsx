/**
 * One row of an evidence chain: an EvidenceChainTag plus its body. Shared
 * layout between ReportTraceabilityPanel and EvidenceDossier so the two
 * presentations of the same conclusion -> gate -> metric -> evidence ->
 * human chain never drift into two different row implementations.
 */
import type { ReactNode } from "react";

export default function ChainStep({ children }: { children: ReactNode }) {
  return <div className="chain-step">{children}</div>;
}
