import { useEffect, useState } from "react";
import { Alert, ApiError, getAlerts } from "./api";
import { SkeletonRows } from "./Skeleton";
import { AlertIcon, FlagIcon } from "./icons";

const SEVERITY_COLOR: Record<Alert["severity"], string> = {
  high: "var(--danger)",
  medium: "var(--medium)",
  low: "var(--low)",
};

const TYPE_LABELS: Record<Alert["alert_type"], string> = {
  high_confidence_actor: "High-confidence attribution",
  new_linkage: "New actor linkage",
  correlation: "Correlation evidence",
  infra_finding: "Infrastructure finding",
};

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// Every alert here is a real, already-persisted Argus record (Actor /
// AttributionEdge / CorrelationEvidence / InfraFinding) reframed for
// scanning — never a synthetic notification. See AlertOut's docstring in
// app/schemas/dashboard.py.
export default function AlertsView({ onSelectActor }: { onSelectActor: (id: string) => void }) {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [severityFilter, setSeverityFilter] = useState<Alert["severity"] | "all">("all");

  useEffect(() => {
    setError(null);
    getAlerts(50)
      .then(setAlerts)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load alerts"));
  }, [retryToken]);

  const filtered = alerts?.filter((a) => severityFilter === "all" || a.severity === severityFilter);

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>Alerts</h2>
        <p className="muted">
          Derived directly from real attribution and correlation activity — a new actor linkage,
          a high-confidence attribution, a threat-intelligence correlation, or an infrastructure
          finding. Every alert traces back to an underlying record; nothing here is a synthetic
          notification.
        </p>
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
        <div className="section-card">
          <div className="section-heading">
            <FlagIcon width={16} height={16} />
            <h3>Activity</h3>
            {alerts && <span className="section-count">{alerts.length}</span>}
            <div style={{ marginLeft: "auto", display: "flex", gap: "0.4rem" }}>
              {(["all", "high", "medium", "low"] as const).map((s) => (
                <button
                  key={s}
                  className={severityFilter === s ? "btn-secondary" : "btn-ghost"}
                  style={{ padding: "0.2rem 0.65rem", fontSize: "0.8rem" }}
                  onClick={() => setSeverityFilter(s)}
                >
                  {s === "all" ? "All" : s[0].toUpperCase() + s.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {alerts === null ? (
            <SkeletonRows count={6} />
          ) : filtered!.length === 0 ? (
            <p className="muted">
              {alerts.length === 0
                ? "No derivable alerts yet — alerts appear once actors, linkages, correlations, or infrastructure findings exist."
                : "No alerts at this severity."}
            </p>
          ) : (
            <ul className="timeline-list">
              {filtered!.map((a, i) => (
                <li
                  key={i}
                  onClick={() => a.actor_id && onSelectActor(a.actor_id)}
                  style={{ cursor: a.actor_id ? "pointer" : "default" }}
                >
                  <span className="timeline-dot" style={{ background: SEVERITY_COLOR[a.severity] }} />
                  <div>
                    <div>
                      <span className="muted" style={{ fontSize: "0.78rem", marginRight: "0.5rem" }}>
                        {TYPE_LABELS[a.alert_type]}
                      </span>
                      {a.summary}
                    </div>
                    <div className="muted" style={{ fontSize: "0.8rem" }}>
                      {timeAgo(a.occurred_at)}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
