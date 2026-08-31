import { useEffect, useState } from "react";
import { ApiError, DataSourceStatus, SystemStatus, getSourceRegistry, getSystemStatus } from "./api";
import { SkeletonRows } from "./Skeleton";
import { ActivityIcon, AlertIcon } from "./icons";

function StatusDot({ healthy }: { healthy: boolean }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: healthy ? "var(--high)" : "var(--danger)",
        boxShadow: healthy ? "0 0 6px var(--high)" : "0 0 6px var(--danger)",
        marginRight: "0.5rem",
      }}
    />
  );
}

// PS-26151 "autonomous/continuous intelligence pipeline". Two real, live
// panels: (1) component health, checked at request time — never a static
// "all green" placeholder; (2) source ingestion status, reusing the exact
// same registry SourcesView reads. Deliberately does NOT show a "recent
// jobs" table: Argus's AnalysisJob model exists but nothing in the pipeline
// writes to it yet, so a job-history list here would be fabricated. Celery
// task status IS real and inspectable per-submission via GET
// /api/jobs/{task_id} (see SubmitLeadView / DemoScenarioView), which is
// noted below instead of faked as a list.
export default function JobsScansView() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [sources, setSources] = useState<DataSourceStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    setError(null);
    Promise.all([getSystemStatus(), getSourceRegistry()])
      .then(([s, src]) => {
        setStatus(s);
        setSources(src);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load system status"));
  }, [retryToken]);

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>Jobs &amp; Scans</h2>
        <p className="muted">
          Live status of Argus's collection and analysis pipeline — component health checked at
          request time, and per-source ingestion state from the same registry Sources &amp; Feeds
          reads.
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
        <>
          <div className="section-card" style={{ marginBottom: "1.5rem" }}>
            <div className="section-heading">
              <ActivityIcon width={16} height={16} />
              <h3>System Status</h3>
              {status && (
                <span className="muted" style={{ marginLeft: "auto", fontSize: "0.8rem" }}>
                  Checked {new Date(status.checked_at).toLocaleTimeString()}
                </span>
              )}
            </div>
            {status === null ? (
              <SkeletonRows count={2} />
            ) : (
              <div className="stat-grid">
                <div className="stat-tile">
                  <div className="stat-tile-label">API</div>
                  <div className="stat-tile-value" style={{ fontSize: "1.1rem" }}>
                    <StatusDot healthy={true} />
                    Online
                  </div>
                </div>
                {status.components.map((c) => (
                  <div className="stat-tile" key={c.name}>
                    <div className="stat-tile-label">{c.name}</div>
                    <div className="stat-tile-value" style={{ fontSize: "1.1rem" }}>
                      <StatusDot healthy={c.healthy} />
                      {c.healthy ? "Online" : "Unreachable"}
                    </div>
                    {c.detail && (
                      <div className="muted" style={{ fontSize: "0.78rem", marginTop: "0.3rem" }}>
                        {c.detail}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="section-card" style={{ marginBottom: "1.5rem" }}>
            <div className="section-heading">
              <h3>Source Ingestion</h3>
              {sources && <span className="section-count">{sources.length}</span>}
            </div>
            {sources === null ? (
              <SkeletonRows count={4} />
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Records Ingested</th>
                    <th>Last Sync</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((s) => (
                    <tr key={s.key}>
                      <td>{s.label}</td>
                      <td>
                        {!s.configured
                          ? "Not configured"
                          : s.record_count === 0
                          ? "Awaiting first ingest"
                          : "Ingested"}
                      </td>
                      <td>{s.record_count.toLocaleString()}</td>
                      <td>
                        {s.most_recent_at ? new Date(s.most_recent_at).toLocaleString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="section-card">
            <div className="section-heading">
              <h3>Analysis Jobs</h3>
            </div>
            <p className="muted">
              Lead analysis, correlation, and attribution recomputation run asynchronously via
              Celery on every lead submission (see Submit Lead / Controlled Demo) — each
              submission returns a task id you can poll at{" "}
              <code>GET /api/jobs/&#123;task_id&#125;</code> for real-time status. Argus does not
              yet persist a queryable history of past jobs, so a "recent jobs" list is
              intentionally not shown here rather than fabricated.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
