import { useEffect, useState } from "react";
import { ActorSearchResult, listActors } from "./api";
import ConfidenceBadge from "./ConfidenceBadge";
import { SkeletonRows } from "./Skeleton";

export default function AttributionView({ onSelectActor }: { onSelectActor: (id: string) => void }) {
  const [actors, setActors] = useState<ActorSearchResult[] | null>(null);

  useEffect(() => {
    listActors()
      .then((r) => setActors(r.items))
      .catch(() => setActors([]));
  }, []);

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>AI Attribution</h2>
        <p className="muted">
          Every actor below is a real cluster derived by the attribution pipeline (shared
          wallet/PGP key + stylometric similarity + infrastructure leaks, weighted). Open an
          actor to see the specific evidence behind its confidence score.
        </p>
      </div>
      <div className="section-card">
        {actors === null ? (
          <SkeletonRows count={6} />
        ) : actors.length === 0 ? (
          <p className="muted">No actors derived yet — submit a lead to run attribution.</p>
        ) : (
          <ul className="dashboard-actor-list">
            {actors.map((a) => (
              <li key={a.id} onClick={() => onSelectActor(a.id)}>
                <span className="dashboard-actor-label">{a.label}</span>
                <ConfidenceBadge score={a.confidence_score} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
