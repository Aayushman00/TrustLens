export default function DimensionProgressChip({
  label,
  done,
}: {
  label: string;
  done: boolean;
}) {
  return (
    <span className="dimension-status-chip">
      <span aria-hidden="true">{done ? "✓" : "○"}</span> {label}
    </span>
  );
}
