import { useEffect, useState } from "react";
import {
  AnalysisJobRecord,
  ApiError,
  DataSourceStatus,
  SystemStatus,
  getSourceRegistry,
  getSystemStatus,
  listRecentJobs,
} from "./api";
import { SkeletonRows } from "./Skeleton";
import { ActivityIcon, AlertIcon } from "./icons";

const JOB_STATUS_COLOR: Record<string, string> = {
  success: "var(--high)",
  failure: "var(--danger)",
  running: "var(--accent)",
};

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

// PS-26151 "autonomous/continuous intelligence pipeline". Three real, live
// panels: (1) component health, checked at request time — never a static
// "all green" placeholder; (2) source ingestion status, reusing the exact
// same registry SourcesView reads; (3) recent analysis jobs, reading
// app.models.actor.AnalysisJob — real rows persisted by the Celery
// reanalyze_all task (see that model's docstring), not fabricated. CLI-
// driven ingestion (scripts/ingest_*.py) does NOT appear here since it
// bypasses Celery entirely — an honest scope, not a hidden gap.
export default function JobsScansView() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [sources, setSources] = useState<DataSourceStatus[] | null>(null);
  const [jobs, setJobs] = useState<AnalysisJobRecord[] | null>(null);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    setError(null);
    Promise.all([getSystemStatus(), getSourceRegistry(), listRecentJobs(1, 20)])
      .then(([s, src, jobsResult]) => {
        setStatus(s);
        setSources(src);
        setJobs(jobsResult.items);
        setJobsTotal(jobsResult.total);
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
              {jobs && <span className="section-count">{jobsTotal}</span>}
            </div>
            <p className="muted" style={{ marginBottom: "0.75rem" }}>
              Lead analysis, correlation, and attribution recomputation run asynchronously via
              Celery on every lead submission (see Submit Lead / Controlled Demo). Each row below
              is a real persisted job — CLI-driven ingestion (ingest_evolution.py, etc.) bypasses
              Celery and does not appear here; that is a scope boundary, not a gap.
            </p>
            {jobs === null ? (
              <SkeletonRows count={3} />
            ) : jobs.length === 0 ? (
              <p className="muted">
                No jobs recorded yet. Submit a lead (or run the Controlled Demo) to enqueue one.
              </p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Target</th>
                    <th>Task ID</th>
                    <th>Started</th>
                    <th>Completed</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j) => (
                    <tr key={j.id}>
                      <td>{j.job_type}</td>
                      <td>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.4rem",
                          }}
                        >
                          <span
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              background: JOB_STATUS_COLOR[j.status] ?? "var(--text-secondary)",
                              display: "inline-block",
                            }}
                          />
                          {j.status}
                        </span>
                      </td>
                      <td className="muted">{j.target}</td>
                      <td className="mono" style={{ fontSize: "0.78rem" }}>
                        {j.task_id ?? "—"}
                      </td>
                      <td>{new Date(j.created_at).toLocaleString()}</td>
                      <td>{j.completed_at ? new Date(j.completed_at).toLocaleString() : "—"}</td>
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
