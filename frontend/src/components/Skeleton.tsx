export function SkeletonRows({ rows = 6, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="skeleton-rows" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row">
          <span className="skeleton" style={{ width: 60 }} />
          <span className="skeleton" style={{ flex: 1, maxWidth: 260 + ((i * 37) % 120) }} />
          <span className="skeleton" style={{ width: 80, marginLeft: "auto" }} />
        </div>
      ))}
    </div>
  );
}

export function SkeletonBlock({ height = 120 }: { height?: number }) {
  return <div className="skeleton" style={{ height, width: "100%" }} aria-hidden />;
}
