import { useEffect, useState } from "react";
import { BreachRecord, DataSourceStatus, getBreachRecords, getSourceRegistry } from "./api";
import { SkeletonRows } from "./Skeleton";

const CATEGORY_LABELS: Record<DataSourceStatus["category"], string> = {
  historical: "Historical dataset",
  continuously_refreshed: "Continuously refreshed",
  feed: "Feed-based",
  api: "API (enrichment)",
};

export default function SourcesView() {
  const [registry, setRegistry] = useState<DataSourceStatus[] | null>(null);
  const [breaches, setBreaches] = useState<BreachRecord[] | null>(null);

  useEffect(() => {
    getSourceRegistry().then(setRegistry).catch(() => setRegistry([]));
    getBreachRecords(100).then(setBreaches).catch(() => setBreaches([]));
  }, []);

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>Sources & Feeds</h2>
        <p className="muted">
          Real record counts and most-recent-observation timestamps from Argus's own tables for
          each connected external resource — never a fabricated "online/offline" indicator.
          Historical datasets (DarkForums, Evolution) reflect a fixed point-in-time sample, not
          live activity.
        </p>
      </div>

      <div className="section-card" style={{ marginBottom: "1.5rem" }}>
        <div className="section-heading">
          <h3>Data Source Registry</h3>
          {registry && <span className="section-count">{registry.length}</span>}
        </div>
        {registry === null ? (
          <SkeletonRows count={5} />
        ) : (
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Category</th>
                <th>Records held</th>
                <th>Most recent</th>
              </tr>
            </thead>
            <tbody>
              {registry.map((s) => (
                <tr key={s.key}>
                  <td>{s.label}</td>
                  <td>{CATEGORY_LABELS[s.category]}</td>
                  <td>{s.record_count.toLocaleString()}</td>
                  <td>
                    {s.record_count === 0
                      ? "Not yet ingested"
                      : s.most_recent_at
                      ? new Date(s.most_recent_at).toLocaleString()
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section-card">
        <div className="section-heading">
          <h3>Breach Directory (Have I Been Pwned)</h3>
          {breaches && <span className="section-count">{breaches.length}</span>}
        </div>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          Public breach metadata only — names, dates, scale, and what categories of data were
          exposed. This is not a record of any specific person or email address; HIBP's
          per-email lookup requires a paid key Argus doesn't hold.
        </p>
        {breaches === null ? (
          <SkeletonRows count={6} />
        ) : breaches.length === 0 ? (
          <p className="muted">
            No breach data ingested yet — run <code>scripts/ingest_hibp.py</code>.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Breach</th>
                <th>Domain</th>
                <th>Breach date</th>
                <th>Accounts affected</th>
                <th>Data exposed</th>
              </tr>
            </thead>
            <tbody>
              {breaches.map((b) => (
                <tr key={b.name}>
                  <td>{b.name}</td>
                  <td>{b.domain ?? "—"}</td>
                  <td>{b.breach_date ?? "—"}</td>
                  <td>{b.pwn_count.toLocaleString()}</td>
                  <td>{b.data_classes.slice(0, 3).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
