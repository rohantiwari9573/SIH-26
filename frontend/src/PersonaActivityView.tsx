import { useEffect, useState } from "react";
import { ApiError, PersonaActivity, getIdentifierActivity } from "./api";
import Badge, { BadgeVariant } from "./Badge";
import { SkeletonRows } from "./Skeleton";
import { AlertIcon } from "./icons";

// Shared by Marketplaces and Forums — both are the same underlying shape
// (real Identifier rows scoped to a caller-chosen set of source_platform
// values), so this is one real implementation reused twice, not two
// near-duplicate pages. See HISTORICAL_PLATFORMS in ActorProfileView.tsx —
// the same real/synthetic classification is reused here rather than
// re-derived, so the two views never contradict each other.
const HISTORICAL_PLATFORMS = new Set(["evolution_market", "evolution_forum", "darkforums_demo_overlay"]);

function platformBadgeVariant(platform: string): BadgeVariant {
  return HISTORICAL_PLATFORMS.has(platform) ? "historical" : "synthetic";
}

export default function PersonaActivityView({
  title,
  description,
  icon,
  platforms,
  platformLabels,
  onSelectActor,
}: {
  title: string;
  description: string;
  icon: JSX.Element;
  platforms: string[];
  platformLabels: Record<string, string>;
  onSelectActor: (id: string) => void;
}) {
  const [data, setData] = useState<PersonaActivity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [query, setQuery] = useState("");

  useEffect(() => {
    setError(null);
    setData(null);
    getIdentifierActivity(platforms, 300)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : `Failed to load ${title.toLowerCase()}`));
    // platforms is a stable literal array from the calling view, not
    // recomputed per render, so it's safe to omit from deps here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryToken]);

  const records = data?.records.filter((r) => {
    if (!query.trim()) return true;
    const q = query.trim().toLowerCase();
    return r.value.toLowerCase().includes(q) || (r.actor_label ?? "").toLowerCase().includes(q);
  });

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>{title}</h2>
        <p className="muted">{description}</p>
      </div>

      {error && (
        <p className="error" style={{ marginBottom: "1.5rem" }}>
          <AlertIcon width={15} height={15} />
          {error}
          <button className="btn-ghost" style={{ marginLeft: "0.75rem" }} onClick={() => setRetryToken((t) => t + 1)}>
            Retry
          </button>
        </p>
      )}

      {!error && (
        <>
          <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
            <div className="stat-tile">
              <div className="stat-tile-label">Records</div>
              <div className="stat-tile-value">{data ? data.summary.total_records : "—"}</div>
            </div>
            <div className="stat-tile">
              <div className="stat-tile-label">Unique Handles</div>
              <div className="stat-tile-value">{data ? data.summary.unique_handles : "—"}</div>
            </div>
            <div className="stat-tile">
              <div className="stat-tile-label">Linked Actors</div>
              <div className="stat-tile-value">{data ? data.summary.linked_actors : "—"}</div>
            </div>
            <div className="stat-tile">
              <div className="stat-tile-label">PGP Keys</div>
              <div className="stat-tile-value">{data ? data.summary.pgp_keys : "—"}</div>
            </div>
            <div className="stat-tile">
              <div className="stat-tile-label">Wallets</div>
              <div className="stat-tile-value">{data ? data.summary.wallets : "—"}</div>
            </div>
          </div>

          {data && data.summary.by_source.length > 0 && (
            <div className="section-card" style={{ marginBottom: "1.5rem" }}>
              <div className="section-heading">
                <h3>Source Breakdown</h3>
              </div>
              <div className="source-bars">
                {data.summary.by_source.map((s) => (
                  <div key={s.source_platform} className="source-bar-row">
                    <span className="source-bar-label">
                      {platformLabels[s.source_platform] ?? s.source_platform}
                    </span>
                    <div className="source-bar-track">
                      <div
                        className="source-bar-fill"
                        style={{ width: `${(s.count / data.summary.total_records) * 100}%` }}
                      />
                    </div>
                    <span className="source-bar-count">{s.count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="section-card">
            <div className="section-heading">
              {icon}
              <h3>Activity</h3>
              {data && <span className="section-count">{data.records.length}</span>}
            </div>

            {data && data.records.length > 0 && (
              <input
                placeholder="Filter by handle or actor..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                style={{ marginBottom: "1rem", width: "100%" }}
              />
            )}

            {data === null ? (
              <SkeletonRows count={5} />
            ) : data.records.length === 0 ? (
              <p className="muted">No records ingested yet for this source set.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Handle / Value</th>
                    <th>Source</th>
                    <th>Actor</th>
                    <th>Identifier</th>
                    <th>Last Observed</th>
                  </tr>
                </thead>
                <tbody>
                  {records!.map((r, i) => (
                    <tr
                      key={i}
                      onClick={() => r.actor_id && onSelectActor(r.actor_id)}
                      style={{ cursor: r.actor_id ? "pointer" : "default" }}
                    >
                      <td className="mono">{r.value}</td>
                      <td>
                        {platformLabels[r.source_platform] ?? r.source_platform}{" "}
                        <Badge variant={platformBadgeVariant(r.source_platform)} />
                      </td>
                      <td>{r.actor_label ?? "—"}</td>
                      <td>{r.identifier_type}</td>
                      <td>{new Date(r.last_seen).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
