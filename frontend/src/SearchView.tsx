import { FormEvent, useEffect, useState } from "react";
import { ActorSearchResult, ApiError, listActors, searchActors } from "./api";
import ConfidenceBadge from "./ConfidenceBadge";

export default function SearchView({
  onSelectActor,
}: {
  onSelectActor: (actorId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ActorSearchResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listActors()
      .then(setResults)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load actors"))
      .finally(() => setLoading(false));
  }, []);

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

  return (
    <div>
      <form className="search-bar" onSubmit={handleSearch}>
        <input
          type="text"
          placeholder="Search by username, wallet, or PGP key..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="submit">Search</button>
      </form>

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Loading...</p>}

      {!loading && results.length === 0 && (
        <p className="muted">No actors found. Run the attribution pipeline to populate data.</p>
      )}

      <ul className="actor-list">
        {results.map((actor) => (
          <li key={actor.id} className="actor-row" onClick={() => onSelectActor(actor.id)}>
            <div>
              <strong>{actor.label}</strong>
              {actor.matched_identifier && (
                <span className="muted"> — matched "{actor.matched_identifier}"</span>
              )}
            </div>
            <ConfidenceBadge score={actor.confidence_score} />
          </li>
        ))}
      </ul>
    </div>
  );
}
