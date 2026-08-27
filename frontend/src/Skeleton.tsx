export function SkeletonRows({ count = 3 }: { count?: number }) {
  return (
    <div>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton skeleton-row" />
      ))}
    </div>
  );
}

export function SkeletonBlock({ height = 220 }: { height?: number }) {
  return <div className="skeleton skeleton-block" style={{ height }} />;
}
