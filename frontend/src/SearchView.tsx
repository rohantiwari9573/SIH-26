import { FormEvent, useEffect, useState } from "react";
import { ActorSearchResult, ApiError, listActors, searchActors } from "./api";
import ConfidenceBadge from "./ConfidenceBadge";
import { AlertIcon, InboxIcon, SearchIcon, UserIcon } from "./icons";
import { SkeletonRows } from "./Skeleton";

export default function SearchView({
  onSelectActor,
}: {
  onSelectActor: (actorId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ActorSearchResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    setError(null);
    setLoading(true);
    listActors()
      .then(setResults)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load actors"))
      .finally(() => setLoading(false));
  }, [retryToken]);

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = query.trim() ? await searchActors(query.trim()) : await listActors();
      setResults(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  const highConfidence = results.filter((r) => r.confidence_score >= 0.7).length;

  return (
    <div>
      <form className="search-bar" onSubmit={handleSearch}>
        <div className="search-input-wrap">
          <SearchIcon width={16} height={16} />
          <input
            type="text"
            placeholder="Search by username, wallet, or PGP key..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <button type="submit">Search</button>
      </form>

      {!loading && !error && results.length > 0 && (
        <div className="stat-strip">
          <span className="stat-chip">
            <strong>{results.length}</strong>&nbsp;actor{results.length === 1 ? "" : "s"}
          </span>
          <span className="stat-chip">
            <strong>{highConfidence}</strong>&nbsp;high-confidence
          </span>
        </div>
      )}

      {error && (
        <p className="error">
          <AlertIcon width={15} height={15} />
          {error}
          <button className="btn-ghost" style={{ marginLeft: "0.75rem" }} onClick={() => setRetryToken((t) => t + 1)}>
            Retry
          </button>
        </p>
      )}

      {loading && <SkeletonRows count={4} />}

      {!loading && !error && results.length === 0 && (
        <div className="empty-state">
          <InboxIcon width={32} height={32} />
          <div>
            <strong>No actors found</strong>
            <p className="muted" style={{ marginTop: "0.25rem" }}>
              Run the attribution pipeline or submit a lead to populate data.
            </p>
          </div>
        </div>
      )}

      <ul className="actor-list">
        {results.map((actor) => (
          <li key={actor.id} className="actor-row" onClick={() => onSelectActor(actor.id)}>
            <div className="actor-row-main">
              <div className="actor-avatar">
                <UserIcon width={17} height={17} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div className="actor-row-title">{actor.label}</div>
                {actor.matched_identifier && (
                  <div className="actor-row-sub">matched &ldquo;{actor.matched_identifier}&rdquo;</div>
                )}
              </div>
            </div>
            <ConfidenceBadge score={actor.confidence_score} />
          </li>
        ))}
      </ul>
    </div>
  );
}
