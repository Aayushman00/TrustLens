export default function Skeleton({
  rows = 4,
  height = "1.4rem",
}: {
  rows?: number;
  height?: string;
}) {
  return (
    <div className="skeleton" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-block" style={{ height }} />
      ))}
    </div>
  );
}
