import { useEffect, useState } from "react";
import {
  ActorSearchResult,
  DashboardStats,
  InfraFindingRow,
  SourceBreakdownItem,
  TimelineEvent,
  TopLink,
  getDashboardStats,
  getDashboardTimeline,
  getInfraFindingsGlobal,
  getSourceBreakdown,
  getTopLink,
  listActors,
} from "./api";
import ConfidenceBadge from "./ConfidenceBadge";
import { SkeletonBlock, SkeletonRows } from "./Skeleton";
import { AlertIcon, LinkIcon, ServerIcon } from "./icons";

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function StatCardTile({
  label,
  value,
  trendPct,
}: {
  label: string;
  value: number;
  trendPct: number | null;
}) {
  return (
    <div className="stat-tile">
      <div className="stat-tile-label">{label}</div>
      <div className="stat-tile-value">{value.toLocaleString()}</div>
      {trendPct !== null ? (
        <div className={`stat-tile-trend ${trendPct >= 0 ? "up" : "down"}`}>
          {trendPct >= 0 ? "↑" : "↓"} {Math.abs(trendPct).toFixed(1)}% vs last 7 days
        </div>
      ) : (
        <div className="stat-tile-trend muted">not enough history yet</div>
      )}
    </div>
  );
}

export default function DashboardView({ onSelectActor }: { onSelectActor: (id: string) => void }) {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [topActors, setTopActors] = useState<ActorSearchResult[]>([]);
  const [topLink, setTopLink] = useState<TopLink | null | undefined>(undefined);
  const [findings, setFindings] = useState<InfraFindingRow[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [sources, setSources] = useState<SourceBreakdownItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      getDashboardStats(),
      listActors(),
      getTopLink(),
      getInfraFindingsGlobal(6),
      getDashboardTimeline(6),
      getSourceBreakdown(),
    ])
      .then(([s, actors, link, infra, tl, src]) => {
        setStats(s);
        setTopActors(actors.slice(0, 5));
        setTopLink(link);
        setFindings(infra);
        setTimeline(tl);
        setSources(src);
      })
      .catch(() => setError("Failed to load dashboard data"));
  }, []);

  if (error) {
    return (
      <p className="error">
        <AlertIcon width={15} height={15} />
        {error}
      </p>
    );
  }

  const sourceTotal = sources.reduce((sum, s) => sum + s.count, 0);

  return (
    <div className="dashboard">
      <div className="stat-grid">
        {stats ? (
          <>
            <StatCardTile {...stats.threat_actors} trendPct={stats.threat_actors.trend_pct} value={stats.threat_actors.value} label={stats.threat_actors.label} />
            <StatCardTile {...stats.unique_handles} trendPct={stats.unique_handles.trend_pct} value={stats.unique_handles.value} label={stats.unique_handles.label} />
            <StatCardTile {...stats.pgp_keys} trendPct={stats.pgp_keys.trend_pct} value={stats.pgp_keys.value} label={stats.pgp_keys.label} />
            <StatCardTile {...stats.wallets_tracked} trendPct={stats.wallets_tracked.trend_pct} value={stats.wallets_tracked.value} label={stats.wallets_tracked.label} />
            <StatCardTile {...stats.attribution_links} trendPct={stats.attribution_links.trend_pct} value={stats.attribution_links.value} label={stats.attribution_links.label} />
            <StatCardTile {...stats.high_confidence_links} trendPct={stats.high_confidence_links.trend_pct} value={stats.high_confidence_links.value} label={stats.high_confidence_links.label} />
          </>
        ) : (
          <SkeletonRows count={6} />
        )}
      </div>

      <div className="dashboard-grid-3">
        <div className="section-card">
          <div className="section-heading">
            <ServerIcon width={16} height={16} />
            <h3>Attribution Confidence (Top Actors)</h3>
          </div>
          {topActors.length === 0 ? (
            <p className="muted">No actors derived yet — submit a lead to run attribution.</p>
          ) : (
            <ul className="dashboard-actor-list">
              {topActors.map((a) => (
                <li key={a.id} onClick={() => onSelectActor(a.id)}>
                  <span className="dashboard-actor-label">{a.label}</span>
                  <ConfidenceBadge score={a.confidence_score} />
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="section-card">
          <div className="section-heading">
            <LinkIcon width={16} height={16} />
            <h3>AI Persona Linking</h3>
          </div>
          {topLink === undefined ? (
            <SkeletonBlock height={140} />
          ) : topLink === null ? (
            <p className="muted">No attribution evidence recorded yet.</p>
          ) : (
            <div>
              <div className="persona-link-pair">
                <span>{topLink.username_a}</span>
                <LinkIcon width={14} height={14} />
                <span>{topLink.username_b}</span>
              </div>
              <div className="persona-link-confidence">
                {(topLink.confidence * 100).toFixed(0)}%
                <span className="muted"> likely same actor</span>
              </div>
              <div className="signal-list">
                {topLink.signals.map((s) => (
                  <div key={s.label} className="signal-row">
                    <span className="signal-label">{s.label}</span>
                    <div className="signal-bar">
                      <div className="signal-bar-fill" style={{ width: `${s.value * 100}%` }} />
                    </div>
                    <span className="signal-value">{(s.value * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
              <button
                className="btn-ghost"
                style={{ marginTop: "0.75rem", padding: 0 }}
                onClick={() => onSelectActor(topLink.actor_id)}
              >
                View actor &rarr;
              </button>
            </div>
          )}
        </div>

        <div className="section-card">
          <div className="section-heading">
            <h3>Top Data Sources</h3>
          </div>
          {sources.length === 0 ? (
            <p className="muted">No identifiers ingested yet.</p>
          ) : (
            <div className="source-bars">
              {sources.map((s) => (
                <div key={s.source_platform} className="source-bar-row">
                  <span className="source-bar-label">{s.source_platform}</span>
                  <div className="source-bar-track">
                    <div
                      className="source-bar-fill"
                      style={{ width: `${(s.count / sourceTotal) * 100}%` }}
                    />
                  </div>
                  <span className="source-bar-count">{s.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="dashboard-grid-2">
        <div className="section-card">
          <div className="section-heading">
            <h3>Hidden Service Misconfigurations</h3>
          </div>
          {findings.length === 0 ? (
            <p className="muted">No infrastructure findings recorded yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Onion Address</th>
                  <th>Type</th>
                  <th>Linked Actor</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((f) => (
                  <tr
                    key={f.id}
                    onClick={() => f.actor_id && onSelectActor(f.actor_id)}
                    style={{ cursor: f.actor_id ? "pointer" : "default" }}
                  >
                    <td className="mono">{f.onion_address}</td>
                    <td>{f.finding_type}</td>
                    <td>{f.actor_label ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="section-card">
          <div className="section-heading">
            <h3>Activity Timeline</h3>
          </div>
          {timeline.length === 0 ? (
            <p className="muted">No activity recorded yet.</p>
          ) : (
            <ul className="timeline-list">
              {timeline.map((e, i) => (
                <li key={i}>
                  <span className="timeline-dot" />
                  <div>
                    <div>{e.summary}</div>
                    <div className="muted" style={{ fontSize: "0.8rem" }}>
                      {timeAgo(e.occurred_at)}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
