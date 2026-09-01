import { FormEvent, useEffect, useRef, useState } from "react";
import { ActorSearchResult, ApiError, listActors, searchActors } from "./api";
import ConfidenceBadge from "./ConfidenceBadge";
import { AlertIcon, InboxIcon, SearchIcon, UserIcon } from "./icons";
import { SkeletonRows } from "./Skeleton";

const PAGE_SIZE = 50;

export default function SearchView({
  onSelectActor,
}: {
  onSelectActor: (actorId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [results, setResults] = useState<ActorSearchResult[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);
  // Guards against out-of-order responses: clicking Next/Previous rapidly
  // fires overlapping requests, and network timing doesn't guarantee they
  // resolve in send order — without this, a slower page-N response landing
  // after a faster page-(N+1) response would desync the pager label from
  // what's actually displayed.
  const requestSeqRef = useRef(0);

  // Real server-side pagination for the un-searched browse list — with 141+
  // real actors already past the old hardcoded 100-row cap, loading
  // "everything" into React and hiding the rest client-side would silently
  // drop real actors from view. Search (a substring match, not a browse)
  // stays as its own server-capped-at-50 endpoint — see api.ts.
  useEffect(() => {
    if (activeQuery) return;
    const seq = ++requestSeqRef.current;
    setError(null);
    setLoading(true);
    listActors(page, PAGE_SIZE)
      .then((r) => {
        if (requestSeqRef.current !== seq) return; // superseded by a newer request
        setResults(r.items);
        setTotal(r.total);
      })
      .catch((err) => {
        if (requestSeqRef.current !== seq) return;
        setError(err instanceof ApiError ? err.message : "Failed to load actors");
      })
      .finally(() => {
        if (requestSeqRef.current === seq) setLoading(false);
      });
  }, [page, activeQuery, retryToken]);

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    const seq = ++requestSeqRef.current; // supersede any in-flight browse-effect request
    setError(null);
    setLoading(true);
    const trimmed = query.trim();
    setActiveQuery(trimmed);
    setPage(1);
    try {
      if (trimmed) {
        const data = await searchActors(trimmed);
        if (requestSeqRef.current !== seq) return;
        setResults(data);
        setTotal(null);
      } else {
        const data = await listActors(1, PAGE_SIZE);
        if (requestSeqRef.current !== seq) return;
        setResults(data.items);
        setTotal(data.total);
      }
    } catch (err) {
      if (requestSeqRef.current !== seq) return;
      setError(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      if (requestSeqRef.current === seq) setLoading(false);
    }
  }

  const highConfidence = results.filter((r) => r.confidence_score >= 0.7).length;
  const totalPages = total !== null ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : 1;

  return (
    <div>
      <div style={{ marginBottom: "1.25rem" }}>
        <h2>Threat Actors</h2>
        <p className="muted">Search resolved actors by handle, wallet, or PGP key.</p>
      </div>

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
            <strong>{total ?? results.length}</strong>&nbsp;actor{(total ?? results.length) === 1 ? "" : "s"}
            {total !== null && total > results.length && (
              <span className="muted"> (showing {results.length})</span>
            )}
          </span>
          <span className="stat-chip">
            <strong>{highConfidence}</strong>&nbsp;high-confidence{activeQuery ? "" : " on this page"}
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

      {!loading && !error && !activeQuery && total !== null && totalPages > 1 && (
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
