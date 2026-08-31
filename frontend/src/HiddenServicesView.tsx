import { useEffect, useState } from "react";
import { ApiError, HiddenServices, getHiddenServices } from "./api";
import { SkeletonRows } from "./Skeleton";
import { AlertIcon, GlobeIcon } from "./icons";

// PS-26151 capability A: Tor hidden-service / infrastructure deanonymization.
// Every row here is a real InfraFinding from app.services.infra_scan
// (SSL cert reuse, banner leaks, default pages) plus whatever real
// deterministic correlation evidence (app.services.correlation) points at
// it — never a claim that a Tor relay itself is a hidden service.
function findingDetailSummary(finding_type: string, detail: Record<string, unknown>): string {
  if (finding_type === "ssl_leak") {
    const cn = detail.subject_cn as string | undefined;
    const san = (detail.san as string[] | undefined) ?? [];
    return cn ? `CN: ${cn}${san.length ? ` (+${san.length} SAN)` : ""}` : "Certificate leak";
  }
  if (finding_type === "banner") {
    const server = detail.server as string | undefined;
    return server ? `Server: ${server}` : "Banner leak";
  }
  return Object.keys(detail).length ? JSON.stringify(detail) : "—";
}

export default function HiddenServicesView({
  onSelectActor,
}: {
  onSelectActor: (id: string) => void;
}) {
  const [data, setData] = useState<HiddenServices | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [query, setQuery] = useState("");

  useEffect(() => {
    setError(null);
    getHiddenServices(100)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load hidden services intelligence"));
  }, [retryToken]);

  const rows = data?.rows.filter((r) => {
    if (!query.trim()) return true;
    const q = query.trim().toLowerCase();
    return (
      r.onion_address.toLowerCase().includes(q) ||
      (r.resolved_ip ?? "").toLowerCase().includes(q) ||
      (r.actor_label ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>Hidden Services Intelligence</h2>
        <p className="muted">
          Real infrastructure findings from Argus's own scan pillar (SSL certificate reuse,
          server banners, default pages) — the operational-security mistakes that tie a hidden
          service back to real-world infrastructure. Correlated against live Tor Onionoo / MISP
          data where a genuine exact-value match exists.
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
          <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
            <div className="stat-tile">
              <div className="stat-tile-label">Hidden Services</div>
              <div className="stat-tile-value">{data ? data.summary.hidden_services : "—"}</div>
            </div>
            <div className="stat-tile">
              <div className="stat-tile-label">Infrastructure Findings</div>
              <div className="stat-tile-value">
                {data ? data.summary.infrastructure_findings : "—"}
              </div>
            </div>
            <div className="stat-tile">
              <div className="stat-tile-label">Clearnet/Infra Correlations</div>
              <div className="stat-tile-value">{data ? data.summary.correlations : "—"}</div>
            </div>
            <div className="stat-tile">
              <div className="stat-tile-label">Linked Actors</div>
              <div className="stat-tile-value">{data ? data.summary.linked_actors : "—"}</div>
            </div>
          </div>

          <div className="section-card">
            <div className="section-heading">
              <GlobeIcon width={16} height={16} />
              <h3>Investigation Table</h3>
              {data && <span className="section-count">{data.rows.length}</span>}
            </div>

            {data && data.rows.length > 0 && (
              <input
                placeholder="Filter by onion address, IP, or actor..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                style={{ marginBottom: "1rem", width: "100%" }}
              />
            )}

            {data === null ? (
              <SkeletonRows count={4} />
            ) : data.rows.length === 0 ? (
              <p className="muted">
                No infrastructure findings recorded yet — run the infra-scan pillar against a
                controlled target (see docs/ETHICS.md) or submit a lead with a confirmed
                onion_address.
              </p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Onion Address</th>
                    <th>Finding</th>
                    <th>Infrastructure</th>
                    <th>Actor</th>
                    <th>Source</th>
                    <th>Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {rows!.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => r.actor_id && onSelectActor(r.actor_id)}
                      style={{ cursor: r.actor_id ? "pointer" : "default" }}
                    >
                      <td className="mono">{r.onion_address}</td>
                      <td>{r.finding_type}</td>
                      <td className="mono" style={{ maxWidth: 260 }}>
                        {findingDetailSummary(r.finding_type, r.detail)}
                        {r.resolved_ip && (
                          <div className="muted" style={{ fontSize: "0.8rem" }}>
                            IP: {r.resolved_ip}
                          </div>
                        )}
                      </td>
                      <td>{r.actor_label ?? "—"}</td>
                      <td>
                        {r.correlations.length === 0 ? (
                          <span className="muted">infra_scan</span>
                        ) : (
                          r.correlations.map((c, i) => (
                            <div key={i}>
                              infra_scan + <strong>{c.source}</strong>
                            </div>
                          ))
                        )}
                      </td>
                      <td>{new Date(r.discovered_at).toLocaleDateString()}</td>
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
