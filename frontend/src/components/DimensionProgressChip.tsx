export type DimensionProgressState = "done" | "running" | "pending" | "not-applicable";

const ICON: Record<DimensionProgressState, string> = {
  done: "✓",
  running: "●",
  pending: "○",
  // Distinct from "done": the probe ran and finished, but the dimension
  // was never configured for this evaluation, so nothing was measured —
  // "–" reads as "not evaluated," never a checkmark that implies evidence.
  "not-applicable": "–",
};

export default function DimensionProgressChip({
  label,
  state,
}: {
  label: string;
  state: DimensionProgressState;
}) {
  return (
    <span className={`dimension-status-chip dimension-status-chip--${state}`}>
      <span aria-hidden="true" className="dimension-status-chip-icon">
        {ICON[state]}
      </span>{" "}
      {label}
    </span>
  );
}
