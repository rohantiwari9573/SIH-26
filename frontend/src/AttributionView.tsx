import { useEffect, useState } from "react";
import { ActorSearchResult, listActors } from "./api";
import ConfidenceBadge from "./ConfidenceBadge";
import { SkeletonRows } from "./Skeleton";

const PAGE_SIZE = 100;

export default function AttributionView({ onSelectActor }: { onSelectActor: (id: string) => void }) {
  const [actors, setActors] = useState<ActorSearchResult[] | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setActors(null);
    listActors(page, PAGE_SIZE)
      .then((r) => {
        setActors(r.items);
        setTotal(r.total);
      })
      .catch(() => {
        setActors([]);
        setTotal(0);
      });
  }, [page]);

  const totalPages = total !== null ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : 1;

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>AI Attribution</h2>
        <p className="muted">
          Every actor below is a real cluster derived by the attribution pipeline (shared
          wallet/PGP key + stylometric similarity + infrastructure leaks, weighted). Open an
          actor to see the specific evidence behind its confidence score.
          {total !== null && total > PAGE_SIZE && (
            <> Showing page {page} of {totalPages} ({total.toLocaleString()} actors total).</>
          )}
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

      {actors !== null && totalPages > 1 && (
        <div className="pager" role="navigation" aria-label="Actor list pages">
          <button
            className="btn-ghost"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            aria-label="Previous page"
          >
            Previous
          </button>
          <span className="muted" style={{ fontSize: "0.85rem" }}>
            Page {page} of {totalPages}
          </span>
          <button
            className="btn-ghost"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
