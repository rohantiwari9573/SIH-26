export default function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const level = score >= 0.7 ? "high" : score >= 0.4 ? "medium" : "low";
  return (
    <span className={`confidence-badge confidence-${level}`}>
      <span className="confidence-dot" />
      {pct}% confidence
    </span>
  );
}
