import { useEffect, useState } from "react";
import {
  ActorProfile,
  ApiError,
  AttributionBreakdown,
  CorrelationEvidence,
  downloadExport,
  getActorAttributionBreakdown,
  getActorEvidence,
  getActorProfile,
} from "./api";
import Badge from "./Badge";
import ConfidenceBadge from "./ConfidenceBadge";
import GraphView from "./GraphView";
import { SkeletonBlock } from "./Skeleton";
import {
  AlertIcon,
  ArrowLeftIcon,
  DownloadIcon,
  KeyIcon,
  LinkIcon,
  LoaderIcon,
  NetworkIcon,
  PenIcon,
  ServerIcon,
  UserIcon,
  WalletIcon,
} from "./icons";

const EDGE_TYPE_LABELS: Record<string, string> = {
  shared_wallet: "Shared wallet address",
  shared_pgp_key: "Shared PGP key",
  stylometry: "Stylometric similarity",
};

const TYPE_ICON: Record<string, JSX.Element> = {
  username: <UserIcon width={13} height={13} />,
  wallet: <WalletIcon width={13} height={13} />,
  pgp_key: <KeyIcon width={13} height={13} />,
};

const SOURCE_LABELS: Record<string, string> = {
  tor_onionoo: "Tor Onionoo",
  misp_circl_osint: "MISP — CIRCL",
  misp_botvrij_osint: "MISP — botvrij.eu",
  hibp: "HIBP Breach Directory",
};

const EVIDENCE_SECTION_LABELS: Record<CorrelationEvidence["evidence_type"], string> = {
  infrastructure: "Tor Intelligence",
  threat_indicator: "Threat Intelligence (MISP)",
  breach_domain: "Breach Intelligence (HIBP)",
};

// Every correlation-evidence source is a real live/feed intelligence fetch
// (see app.services.correlation) — always LIVE, never historical/synthetic.
// Identifier source_platform values, by contrast, mix historical datasets
// (evolution_market, darkforums_demo_overlay) with Argus's own controlled
// demo platforms (mock_marketplace_*) — see HISTORICAL_PLATFORMS below.
const HISTORICAL_PLATFORMS = new Set(["evolution_market", "evolution_forum", "darkforums_demo_overlay"]);

function platformBadgeVariant(platform: string): "historical" | "synthetic" {
  return HISTORICAL_PLATFORMS.has(platform) ? "historical" : "synthetic";
}

function confidenceBucket(score: number): string {
  if (score >= 0.7) return "High confidence";
  if (score >= 0.4) return "Medium confidence";
  if (score > 0) return "Low confidence";
  return "No linking evidence yet";
}

export default function ActorProfileView({
  actorId,
  onBack,
}: {
  actorId: string;
  onBack: () => void;
}) {
  const [profile, setProfile] = useState<ActorProfile | null>(null);
  const [evidence, setEvidence] = useState<CorrelationEvidence[] | null>(null);
  const [breakdown, setBreakdown] = useState<AttributionBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    setError(null);
    setProfile(null);
    setEvidence(null);
    setBreakdown(null);
    getActorProfile(actorId)
      .then(setProfile)
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Unable to load this actor's intelligence."
        )
      );
    getActorEvidence(actorId)
      .then(setEvidence)
      .catch(() => setEvidence([]));
    getActorAttributionBreakdown(actorId)
      .then(setBreakdown)
      .catch(() => setBreakdown(null));
  }, [actorId, retryToken]);

  async function handleExport(format: "csv" | "json" | "report") {
    setExportError(null);
    setExporting(format);
    try {
      await downloadExport(actorId, format);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : "Export failed");
    } finally {
      setExporting(null);
    }
  }

  if (error) {
    return (
      <div>
        <button className="btn-ghost" onClick={onBack}>
          <ArrowLeftIcon width={16} height={16} />
          Back to search
        </button>
        <p className="error" style={{ marginTop: "1rem" }}>
          <AlertIcon width={15} height={15} />
          {error}
        </p>
        <button onClick={() => setRetryToken((t) => t + 1)}>Retry</button>
      </div>
    );
  }

  if (!profile) {
    return (
      <div>
        <div className="skeleton skeleton-line" style={{ width: 160, height: 32, marginBottom: "1.5rem" }} />
        <div className="skeleton skeleton-line" style={{ width: 280, height: 28, marginBottom: "2rem" }} />
        <SkeletonBlock height={180} />
      </div>
    );
  }

  return (
    <div>
      <button className="btn-ghost" onClick={onBack}>
        <ArrowLeftIcon width={16} height={16} />
        Back to search
      </button>

      <div className="profile-header">
        <div>
          <h2>{profile.label}</h2>
          <div className="profile-subtitle">
            {profile.identifiers.length} identifier{profile.identifiers.length === 1 ? "" : "s"} ·
            {" "}
            last observed {new Date(profile.updated_at).toLocaleString()}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <ConfidenceBadge score={profile.confidence_score} />
          <div className="muted" style={{ fontSize: "0.78rem", marginTop: "0.2rem" }}>
            {confidenceBucket(profile.confidence_score)}
          </div>
        </div>
      </div>

      <section>
        <div className="section-card">
          <div className="section-heading">
            <LinkIcon width={16} height={16} />
            <h3>Why this attribution?</h3>
          </div>
          {breakdown === null ? (
            <SkeletonBlock height={90} />
          ) : (
            <>
              <div className="signal-list">
                {breakdown.signals.map((s) => (
                  <div key={s.label} className="signal-row">
                    <span className="signal-label">{s.label}</span>
                    {s.available ? (
                      <>
                        <div className="signal-bar">
                          <div className="signal-bar-fill" style={{ width: `${s.value * 100}%` }} />
                        </div>
                        <span className="signal-value">{(s.value * 100).toFixed(0)}%</span>
                      </>
                    ) : (
                      <span className="muted" style={{ fontSize: "0.8rem" }}>
                        Not enough evidence
                      </span>
                    )}
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.75rem", fontSize: "0.85rem" }}>
                <span className="muted">
                  Evidence items: <strong>{breakdown.evidence_count}</strong>
                </span>
                <span className="muted">
                  Sources: {breakdown.sources.length > 0 ? breakdown.sources.join(", ") : "—"}
                </span>
              </div>
            </>
          )}
        </div>
      </section>

      <div className="export-bar">
        {(["csv", "json", "report"] as const).map((format) => (
          <button
            key={format}
            className="btn-secondary"
            onClick={() => handleExport(format)}
            disabled={exporting !== null}
          >
            {exporting === format ? (
              <LoaderIcon width={15} height={15} />
            ) : (
              <DownloadIcon width={15} height={15} />
            )}
            {exporting === format ? "Exporting..." : `Export ${format.toUpperCase()}`}
          </button>
        ))}
      </div>
      {exportError && (
        <p className="error" style={{ marginBottom: "1.5rem" }}>
          <AlertIcon width={15} height={15} />
          {exportError}
        </p>
      )}

      <section>
        <div className="section-card">
          <div className="section-heading">
            <UserIcon width={16} height={16} />
            <h3>Identifiers</h3>
            <span className="section-count">{profile.identifiers.length}</span>
          </div>
          {profile.identifiers.length === 0 ? (
            <p className="muted">None recorded.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Value</th>
                  <th>Source platform</th>
                </tr>
              </thead>
              <tbody>
                {profile.identifiers.map((ident) => (
                  <tr key={ident.id}>
                    <td>
                      <span className="type-pill">
                        {TYPE_ICON[ident.identifier_type]}
                        {ident.identifier_type}
                      </span>
                    </td>
                    <td className="mono">{ident.value}</td>
                    <td>
                      {ident.source_platform}{" "}
                      <Badge variant={platformBadgeVariant(ident.source_platform)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section>
        <div className="section-card">
          <div className="section-heading">
            <ServerIcon width={16} height={16} />
            <h3>Infrastructure findings</h3>
            <span className="section-count">{profile.infra_findings.length}</span>
          </div>
          {profile.infra_findings.length === 0 ? (
            <p className="muted">None recorded.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Onion address</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {profile.infra_findings.map((finding) => (
                  <tr key={finding.id}>
                    <td>{finding.finding_type}</td>
                    <td className="mono">{finding.onion_address}</td>
                    <td className="mono">{JSON.stringify(finding.detail)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section>
        <div className="section-card" style={{ padding: 0 }}>
          <div className="section-heading" style={{ padding: "1.5rem 1.5rem 0", marginBottom: "1rem" }}>
            <NetworkIcon width={16} height={16} />
            <h3>Relationship graph</h3>
          </div>
          <GraphView actorId={actorId} profile={profile} evidence={evidence} />
        </div>
      </section>

      <section>
        <div className="section-card">
          <div className="section-heading">
            <LinkIcon width={16} height={16} />
            <h3>Attribution evidence</h3>
            <span className="section-count">{profile.attribution_edges.length}</span>
          </div>
          {profile.attribution_edges.length === 0 ? (
            <div>
              <p style={{ marginBottom: "0.35rem" }}>
                <strong>No linking evidence found.</strong>
              </p>
              <p className="muted">
                This is currently a single-persona actor. This does not indicate the persona is
                unimportant — it indicates no shared wallet, PGP key, or stylometric match to
                another known persona exists in Argus's current dataset.
              </p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Persona A</th>
                  <th>Persona B</th>
                  <th>Evidence</th>
                  <th>Strength</th>
                </tr>
              </thead>
              <tbody>
                {profile.attribution_edges.map((edge) => (
                  <tr key={edge.id}>
                    <td>
                      {edge.username_a} <span className="muted">({edge.platform_a})</span>
                    </td>
                    <td>
                      {edge.username_b} <span className="muted">({edge.platform_b})</span>
                    </td>
                    <td>{EDGE_TYPE_LABELS[edge.edge_type] ?? edge.edge_type}</td>
                    <td>{(edge.weight * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section>
        <div className="section-card">
          <div className="section-heading">
            <ServerIcon width={16} height={16} />
            <h3>Threat &amp; Infrastructure Intelligence</h3>
            <span className="section-count">{evidence?.length ?? 0}</span>
          </div>
          <p className="muted" style={{ marginBottom: "0.75rem" }}>
            Supporting intelligence only — a deterministic match between this actor's confirmed
            infrastructure and a live/feed source. It does not affect the attribution confidence
            above; see each row's source before treating it as anything more than corroborating
            context.
          </p>
          {evidence === null ? (
            <SkeletonBlock height={80} />
          ) : evidence.length === 0 ? (
            <div>
              <p style={{ marginBottom: "0.35rem" }}>
                <strong>No correlations found.</strong>
              </p>
              <p className="muted">
                No deterministic relationship was found between this actor's confirmed
                infrastructure and Tor Onionoo, MISP CIRCL, MISP botvrij.eu, or HIBP. This does
                not indicate absence of threat activity — it indicates that no supported
                observable (shared IP, domain, or hostname) matched the current Argus dataset.
              </p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Source</th>
                  <th>Matched value</th>
                  <th>Description</th>
                  <th>Observed</th>
                </tr>
              </thead>
              <tbody>
                {evidence.map((e) => (
                  <tr key={e.id}>
                    <td>{EVIDENCE_SECTION_LABELS[e.evidence_type] ?? e.evidence_type}</td>
                    <td>
                      {SOURCE_LABELS[e.source] ?? e.source} <Badge variant="live" />
                    </td>
                    <td className="mono">{e.matched_value}</td>
                    <td className="muted">{e.description}</td>
                    <td>{e.observed_at ? new Date(e.observed_at).toLocaleDateString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section>
        <div className="section-card">
          <div className="section-heading">
            <PenIcon width={16} height={16} />
            <h3>Style profiles</h3>
            <span className="section-count">{profile.style_profiles.length}</span>
          </div>
          {profile.style_profiles.length === 0 ? (
            <p className="muted">None recorded.</p>
          ) : (
            <p className="muted">
              {profile.style_profiles.length} stylometric sample
              {profile.style_profiles.length === 1 ? "" : "s"} contributed to the
              behavioral-analysis signal for this actor.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
