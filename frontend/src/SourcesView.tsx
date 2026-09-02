import { useEffect, useState } from "react";
import { BreachRecord, DataSourceStatus, getBreachRecords, getSourceRegistry } from "./api";
import Badge from "./Badge";
import { SkeletonRows } from "./Skeleton";

const CATEGORY_LABELS: Record<DataSourceStatus["category"], string> = {
  historical: "Historical dataset",
  continuously_refreshed: "Continuously refreshed",
  feed: "Feed-based",
  api: "API (enrichment)",
};

// Everything in this file's registry is real (queried live from Argus's own
// tables — see get_source_registry in app/api/routes/dashboard.py), but the
// three "historical" sources and four "live/refreshable" ones behave
// differently for an investigator: a historical source's timestamp is a
// fixed point-in-time snapshot from when it was ingested, while a live
// source's timestamp reflects an actual external fetch that can be re-run.
// Splitting them into two visibly distinct groups (rather than one flat
// table with a category column) makes that difference obvious at a glance
// instead of requiring the reader to parse each row's category text.
const LIVE_CATEGORIES: DataSourceStatus["category"][] = ["continuously_refreshed", "feed", "api"];

// Reasons shown next to each NOT CONFIGURED source. Sourced from the live
// registry (configured=false) wherever a backend row exists; HIBP's
// per-email lookup has no registry row (it's an on-demand check, not a
// bulk-ingested table — see GET /api/dashboard/hibp-lookup) so it's the one
// entry listed here directly rather than derived.
const NOT_CONFIGURED_REASONS: Record<string, string> = {
  urlhaus: "abuse.ch API key not set (URLHAUS_API_KEY)",
  malwarebazaar: "abuse.ch API key not set (MALWAREBAZAAR_API_KEY)",
  chainabuse: "API key not set (CHAINABUSE_API_KEY)",
};

const HIBP_PER_EMAIL_NOTE = {
  key: "hibp_per_email",
  label: "HIBP per-email lookup",
  reason:
    "requires a paid HIBP key (HIBP_API_KEY) — only the public breach directory below is used",
};

// What each source is actually for — shown so an investigator understands
// why a source exists before deciding whether to trust/filter by it.
const SOURCE_PURPOSE: Record<string, string> = {
  tor_onionoo: "Tor relay metadata and infrastructure enrichment.",
  misp_circl_osint: "Threat-intelligence event/indicator feed (CIRCL community).",
  misp_botvrij_osint: "Threat-intelligence event/indicator feed (botvrij.eu/CUDESO), independent of CIRCL.",
  hibp: "Public breach directory metadata (not per-email lookup).",
  darkforums: "Historical forum-persona sample (Zenodo, real post content).",
  evolution_market: "Historical marketplace vendor listings (Evolution Market dataset).",
  evolution_forum: "Historical forum posts (Evolution Market dataset).",
};

const RUN_STATUS_LABELS: Record<NonNullable<DataSourceStatus["last_run_status"]>, string> = {
  ok: "OK",
  failed: "Failed",
  never_run: "Never run",
};

const COLLECTION_MODE_LABELS: Record<DataSourceStatus["collection_mode"], string> = {
  scheduled: "Autonomous (every 6h)",
  manual: "Manual (CLI script)",
  not_applicable: "Fixed snapshot",
};

function SourceTable({ sources, live }: { sources: DataSourceStatus[]; live: boolean }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Source</th>
          <th>Status</th>
          <th>Records</th>
          <th>Last Sync</th>
          <th>Type</th>
          <th>Collection</th>
          <th>Purpose</th>
        </tr>
      </thead>
      <tbody>
        {sources.map((s) => (
          <tr key={s.key}>
            <td>{s.label}</td>
            <td>
              <Badge variant={live ? "live" : "historical"} label={live ? "LIVE" : "HISTORICAL"} />
            </td>
            <td>{s.record_count.toLocaleString()}</td>
            <td>
              {s.record_count === 0
                ? "Not yet ingested"
                : s.most_recent_at
                ? new Date(s.most_recent_at).toLocaleString()
                : "—"}
            </td>
            <td>{CATEGORY_LABELS[s.category]}</td>
            <td>
              {COLLECTION_MODE_LABELS[s.collection_mode]}
              {s.collection_mode === "scheduled" && (
                <div className="muted" style={{ fontSize: "0.78rem" }}>
                  {s.last_run_status && RUN_STATUS_LABELS[s.last_run_status]}
                  {s.next_scheduled_at &&
                    ` · next: ${new Date(s.next_scheduled_at).toLocaleString()}`}
                </div>
              )}
            </td>
            <td className="muted">{SOURCE_PURPOSE[s.key] ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function SourcesView() {
  const [registry, setRegistry] = useState<DataSourceStatus[] | null>(null);
  const [breaches, setBreaches] = useState<BreachRecord[] | null>(null);

  useEffect(() => {
    getSourceRegistry().then(setRegistry).catch(() => setRegistry([]));
    getBreachRecords(100).then(setBreaches).catch(() => setBreaches([]));
  }, []);

  const live = registry?.filter((s) => LIVE_CATEGORIES.includes(s.category) && s.configured) ?? [];
  const historical = registry?.filter((s) => s.category === "historical" && s.configured) ?? [];
  const notConfigured = [
    ...(registry ?? [])
      .filter((s) => !s.configured)
      .map((s) => ({ key: s.key, label: s.label, reason: NOT_CONFIGURED_REASONS[s.key] ?? "credential not set" })),
    HIBP_PER_EMAIL_NOTE,
  ];

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
          <h3>Live / Refreshable Sources</h3>
          {registry && <span className="section-count">{live.length}</span>}
        </div>
        {registry === null ? <SkeletonRows count={4} /> : <SourceTable sources={live} live />}
      </div>

      <div className="section-card" style={{ marginBottom: "1.5rem" }}>
        <div className="section-heading">
          <h3>Historical / Ingested Sources</h3>
          {registry && <span className="section-count">{historical.length}</span>}
        </div>
        {registry === null ? (
          <SkeletonRows count={3} />
        ) : (
          <SourceTable sources={historical} live={false} />
        )}
      </div>

      <div className="section-card" style={{ marginBottom: "1.5rem" }}>
        <div className="section-heading">
          <h3>Not Configured</h3>
          <span className="section-count">{notConfigured.length}</span>
        </div>
        <p className="muted" style={{ marginBottom: "0.75rem" }}>
          Planned resources with no credential set and zero records — shown honestly rather
          than omitted, so the source inventory stays complete. Each ingest script (see
          scripts/ingest_*.py) starts working with no other code changes once its key is set.
        </p>
        <table>
          <thead>
            <tr>
              <th>Source</th>
              <th>Status</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {notConfigured.map((s) => (
              <tr key={s.key}>
                <td>{s.label}</td>
                <td>
                  <span className="type-pill">NOT CONFIGURED</span>
                </td>
                <td className="muted">{s.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
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
