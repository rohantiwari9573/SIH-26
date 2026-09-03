import { useEffect, useRef, useState } from "react";
import {
  ActorAIAnalysis,
  ActorEnrichment,
  ActorProfile,
  ActorThreatActivity,
  ApiError,
  AttributionBreakdown,
  CorrelationEvidence,
  downloadExport,
  getActorAIAnalysis,
  getActorAttributionBreakdown,
  getActorEnrichment,
  getActorEvidence,
  getActorProfile,
  getActorThreatActivity,
} from "./api";
import Badge from "./Badge";
import ConfidenceBadge from "./ConfidenceBadge";
import GraphView from "./GraphView";
import { SkeletonBlock } from "./Skeleton";
import {
  ActivityIcon,
  AlertIcon,
  ArrowLeftIcon,
  CheckIcon,
  ClockIcon,
  DownloadIcon,
  FlagIcon,
  GlobeIcon,
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
  const [threatActivity, setThreatActivity] = useState<ActorThreatActivity | null>(null);
  const [enrichment, setEnrichment] = useState<ActorEnrichment | null>(null);
  const [aiAnalysis, setAiAnalysis] = useState<ActorAIAnalysis | null>(null);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [categoryPages, setCategoryPages] = useState<
    Record<string, { activities: ActorThreatActivity["activities"]; total: number; page: number; loading: boolean }>
  >({});
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  // Shown briefly after a successful export — csv/json resolve in well
  // under a second, so without this the button's loading spinner flashes
  // and reverts before it registers, and the (real, successful) download
  // looks like nothing happened.
  const [downloaded, setDownloaded] = useState<string | null>(null);
  const downloadedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    return () => {
      if (downloadedTimer.current) clearTimeout(downloadedTimer.current);
    };
  }, []);

  useEffect(() => {
    setError(null);
    setProfile(null);
    setEvidence(null);
    setBreakdown(null);
    setThreatActivity(null);
    setEnrichment(null);
    setAiAnalysis(null);
    setExpandedCategory(null);
    setCategoryPages({});
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
    getActorThreatActivity(actorId)
      .then(setThreatActivity)
      .catch(() =>
        setThreatActivity({ summary: [], activities: [], activities_total: 0, page: 1, page_size: 50 })
      );
    getActorEnrichment(actorId)
      .then(setEnrichment)
      .catch(() =>
        setEnrichment({
          platforms: [],
          total_activities: 0,
          classified_activities: 0,
          first_observed: null,
          last_observed: null,
          active_duration_days: null,
          days_since_last_observed: null,
          posting_frequency_per_week: null,
          shared_wallet_across_platforms: false,
          shared_pgp_key_across_platforms: false,
          platform_migration_order: [],
        })
      );
    getActorAIAnalysis(actorId)
      .then(setAiAnalysis)
      .catch(() =>
        setAiAnalysis({
          personas: [],
          pairs: [],
          status_message: "AI analysis temporarily unavailable.",
          method: "",
        })
      );
  }, [actorId, retryToken]);

  const CATEGORY_PAGE_SIZE = 25;
  // Guards against out-of-order responses: rapidly clicking Next/Previous
  // fires overlapping requests for the same category, and network timing
  // doesn't guarantee they resolve in the order they were sent. Each call
  // stamps its own sequence number per category and only applies its
  // result if it's still the most recent request for that category.
  const categoryRequestSeqRef = useRef<Record<string, number>>({});

  async function loadCategoryPage(category: string, page: number) {
    const seq = (categoryRequestSeqRef.current[category] ?? 0) + 1;
    categoryRequestSeqRef.current[category] = seq;

    setCategoryPages((prev) => ({
      ...prev,
      [category]: {
        activities: prev[category]?.activities ?? [],
        total: prev[category]?.total ?? 0,
        page,
        loading: true,
      },
    }));
    try {
      const data = await getActorThreatActivity(actorId, { category, page, pageSize: CATEGORY_PAGE_SIZE });
      if (categoryRequestSeqRef.current[category] !== seq) return; // superseded by a newer request
      setCategoryPages((prev) => ({
        ...prev,
        [category]: { activities: data.activities, total: data.activities_total, page, loading: false },
      }));
    } catch {
      if (categoryRequestSeqRef.current[category] !== seq) return;
      setCategoryPages((prev) => ({
        ...prev,
        [category]: { activities: [], total: 0, page, loading: false },
      }));
    }
  }

  function toggleCategory(category: string) {
    if (expandedCategory === category) {
      setExpandedCategory(null);
      return;
    }
    setExpandedCategory(category);
    if (!categoryPages[category]) {
      loadCategoryPage(category, 1);
    }
  }

  async function handleExport(format: "csv" | "json" | "report") {
    setExportError(null);
    setExporting(format);
    try {
      await downloadExport(actorId, format);
      if (downloadedTimer.current) clearTimeout(downloadedTimer.current);
      setDownloaded(format);
      downloadedTimer.current = setTimeout(() => setDownloaded(null), 1800);
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
          <div className="muted" style={{ fontSize: "0.84rem", marginTop: "0.3rem" }}>
            {confidenceBucket(profile.confidence_score)}
          </div>
        </div>
      </div>

      <div className="stat-strip">
        <span className="stat-chip">
          <strong>{enrichment ? enrichment.platforms.length : "…"}</strong>&nbsp;platform
          {enrichment?.platforms.length === 1 ? "" : "s"} observed
        </span>
        <span className="stat-chip">
          <strong>{enrichment ? enrichment.total_activities : "…"}</strong>&nbsp;activit
          {enrichment?.total_activities === 1 ? "y" : "ies"}
        </span>
        <span className="stat-chip">
          <strong>{profile.identifiers.length}</strong>&nbsp;identifier
          {profile.identifiers.length === 1 ? "" : "s"}
        </span>
        <span className="stat-chip">
          <strong>{threatActivity ? threatActivity.summary.length : "…"}</strong>&nbsp;threat{" "}
          {threatActivity?.summary.length === 1 ? "category" : "categories"}
        </span>
        {enrichment?.first_observed && (
          <span className="stat-chip">
            First observed <strong>{new Date(enrichment.first_observed).toLocaleDateString()}</strong>
          </span>
        )}
        {enrichment?.last_observed && (
          <span className="stat-chip">
            Last observed <strong>{new Date(enrichment.last_observed).toLocaleDateString()}</strong>
          </span>
        )}
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
            ) : downloaded === format ? (
              <CheckIcon width={15} height={15} />
            ) : (
              <DownloadIcon width={15} height={15} />
            )}
            {exporting === format
              ? "Exporting..."
              : downloaded === format
              ? "Downloaded"
              : `Export ${format.toUpperCase()}`}
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
            <ActivityIcon width={16} height={16} />
            <h3>Activity Overview</h3>
          </div>
          <p className="muted" style={{ marginBottom: "0.75rem" }}>
            Derived by aggregating this actor's real ingested activity records (marketplace
            listings, forum posts) — the same records behind the identifiers and threat
            categories above, counted here instead of individually listed.
          </p>
          {enrichment === null ? (
            <SkeletonBlock height={80} />
          ) : enrichment.total_activities === 0 ? (
            <p className="muted">
              No evidence observed in currently ingested sources — this actor's known personas
              have no linked activity records.
            </p>
          ) : (
            <div className="signal-list">
              <div className="signal-row">
                <span className="signal-label">Total activities</span>
                <span className="signal-value">{enrichment.total_activities}</span>
              </div>
              <div className="signal-row">
                <span className="signal-label">Classified into a threat category</span>
                <span className="signal-value">{enrichment.classified_activities}</span>
              </div>
              {enrichment.active_duration_days !== null && (
                <div className="signal-row">
                  <span className="signal-label">Active span</span>
                  <span className="signal-value">{enrichment.active_duration_days} days</span>
                </div>
              )}
              {enrichment.posting_frequency_per_week !== null && (
                <div className="signal-row">
                  <span className="signal-label">Posting frequency</span>
                  <span className="signal-value">
                    {enrichment.posting_frequency_per_week}/week
                  </span>
                </div>
              )}
              {enrichment.days_since_last_observed !== null && (
                <div className="signal-row">
                  <span className="signal-label">Days since last observed</span>
                  <span className="signal-value">{enrichment.days_since_last_observed}</span>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      <section>
        <div className="section-card">
          <div className="section-heading">
            <GlobeIcon width={16} height={16} />
            <h3>Cross-Platform Presence</h3>
            <span className="section-count">{enrichment?.platforms.length ?? 0}</span>
          </div>
          {enrichment === null ? (
            <SkeletonBlock height={80} />
          ) : enrichment.platforms.length === 0 ? (
            <p className="muted">No evidence observed in currently ingested sources.</p>
          ) : (
            <>
              <table>
                <thead>
                  <tr>
                    <th>Platform</th>
                    <th>Identifiers</th>
                    <th>Activities</th>
                    <th>First activity</th>
                    <th>Last activity</th>
                  </tr>
                </thead>
                <tbody>
                  {enrichment.platforms.map((p) => (
                    <tr key={p.platform}>
                      <td>
                        {p.platform} <Badge variant={platformBadgeVariant(p.platform)} />
                      </td>
                      <td>{p.identifier_count}</td>
                      <td>{p.activity_count}</td>
                      <td>{p.first_activity ? new Date(p.first_activity).toLocaleDateString() : "—"}</td>
                      <td>{p.last_activity ? new Date(p.last_activity).toLocaleDateString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: "flex", gap: "1.5rem", marginTop: "0.75rem", fontSize: "0.85rem" }}>
                <span className="muted">
                  Shared wallet across platforms:{" "}
                  <strong>{enrichment.shared_wallet_across_platforms ? "Yes" : "No"}</strong>
                </span>
                <span className="muted">
                  Shared PGP key across platforms:{" "}
                  <strong>{enrichment.shared_pgp_key_across_platforms ? "Yes" : "No"}</strong>
                </span>
              </div>
              {enrichment.platform_migration_order.length > 1 && (
                <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                  <ClockIcon width={13} height={13} /> Observed activity order (earliest first):{" "}
                  {enrichment.platform_migration_order.join(" → ")}
                </p>
              )}
            </>
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
                  <th>Severity</th>
                  <th>Onion address</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {profile.infra_findings.map((finding) => (
                  <tr key={finding.id}>
                    <td>{finding.finding_type}</td>
                    <td>{finding.severity ?? "—"}</td>
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
        <div className="section-card">
          <div className="section-heading">
            <GlobeIcon width={16} height={16} />
            <h3>Suspected Real-World Entities</h3>
            <span className="section-count">{profile.real_world_entities.length}</span>
          </div>
          <p className="muted" style={{ marginBottom: "0.75rem" }}>
            Domains and organizations this actor's infrastructure or external-intelligence
            evidence points toward — derived, never invented, and never a confirmed identity.
            An investigator should independently verify before acting on any row below.
          </p>
          {profile.real_world_entities.length === 0 ? (
            <p className="muted">No evidence available.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Entity</th>
                  <th>Type</th>
                  <th>Confidence</th>
                  <th>Source</th>
                  <th>Explanation</th>
                </tr>
              </thead>
              <tbody>
                {profile.real_world_entities.map((entity) => (
                  <tr key={entity.id}>
                    <td className="mono">{entity.entity_name}</td>
                    <td>{entity.entity_type}</td>
                    <td>{entity.confidence.replace(/_/g, " ")}</td>
                    <td>{entity.source}</td>
                    <td className="muted">{entity.explanation}</td>
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
                    <td className="strength-value">{(edge.weight * 100).toFixed(0)}%</td>
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
            <FlagIcon width={16} height={16} />
            <h3>Observed Threat Categories</h3>
            <span className="section-count">{threatActivity?.summary.length ?? 0}</span>
          </div>
          <p className="muted" style={{ marginBottom: "0.75rem" }}>
            Threat categories derived from this actor's own real activity content (marketplace
            listings, forum posts) — a separate analysis from the attribution evidence above.
            This does not affect attribution confidence, and does not assert the actor
            definitively committed a crime; it reflects what Argus's classifier found in the
            actor's observed activity text and why.
          </p>
          {threatActivity === null ? (
            <SkeletonBlock height={80} />
          ) : threatActivity.summary.length === 0 ? (
            <div>
              <p style={{ marginBottom: "0.35rem" }}>
                <strong>No classifiable activity found.</strong>
              </p>
              <p className="muted">
                None of this actor's known personas have activity text (marketplace listing or
                forum post content) that matched a controlled threat category. This is the
                expected result for actors built only from infrastructure/correlation evidence,
                or whose activity text was too generic/ambiguous to classify conservatively.
              </p>
            </div>
          ) : (
            <div>
              {threatActivity.summary.map((cat) => {
                const isOpen = expandedCategory === cat.category;
                const pageState = categoryPages[cat.category];
                const totalPages = pageState
                  ? Math.max(1, Math.ceil(pageState.total / CATEGORY_PAGE_SIZE))
                  : 1;
                return (
                  <div key={cat.category} className="threat-category-block">
                    <button
                      className="threat-category-row"
                      onClick={() => toggleCategory(cat.category)}
                      aria-expanded={isOpen}
                    >
                      <span className="threat-category-label">{cat.category_label}</span>
                      <span className="muted" style={{ fontSize: "0.85rem" }}>
                        {cat.activity_count} activit{cat.activity_count === 1 ? "y" : "ies"} ·{" "}
                        {cat.sources.length} source{cat.sources.length === 1 ? "" : "s"}
                      </span>
                    </button>
                    {isOpen && (
                      <>
                        {!pageState || pageState.loading ? (
                          <SkeletonBlock height={60} />
                        ) : (
                          <>
                            <table>
                              <thead>
                                <tr>
                                  <th>Source</th>
                                  <th>Persona</th>
                                  <th>Activity</th>
                                  <th>Why classified</th>
                                  <th>Observed</th>
                                </tr>
                              </thead>
                              <tbody>
                                {pageState.activities.map((item) => (
                                  <tr key={item.id}>
                                    <td>
                                      {item.source_platform}{" "}
                                      <Badge variant={platformBadgeVariant(item.source_platform)} />
                                    </td>
                                    <td className="mono">{item.persona_username}</td>
                                    <td>{item.title ?? item.source_record_id}</td>
                                    <td className="muted">
                                      {item.classification_reason}
                                      <span
                                        className="muted"
                                        style={{ display: "block", fontSize: "0.78rem" }}
                                      >
                                        {item.classification_confidence === "high"
                                          ? "High confidence — source-provided category"
                                          : "Medium confidence — keyword rule match"}
                                      </span>
                                    </td>
                                    <td>
                                      {item.observed_at
                                        ? new Date(item.observed_at).toLocaleDateString()
                                        : "—"}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                            {totalPages > 1 && (
                              <div className="pager" style={{ padding: "0.75rem 0" }}>
                                <button
                                  className="btn-ghost"
                                  onClick={() => loadCategoryPage(cat.category, pageState.page - 1)}
                                  disabled={pageState.page <= 1}
                                  aria-label={`Previous page of ${cat.category_label} evidence`}
                                >
                                  Previous
                                </button>
                                <span className="muted" style={{ fontSize: "0.85rem" }}>
                                  Page {pageState.page} of {totalPages}
                                </span>
                                <button
                                  className="btn-ghost"
                                  onClick={() => loadCategoryPage(cat.category, pageState.page + 1)}
                                  disabled={pageState.page >= totalPages}
                                  aria-label={`Next page of ${cat.category_label} evidence`}
                                >
                                  Next
                                </button>
                              </div>
                            )}
                          </>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
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
                  <th>Confidence</th>
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
                    <td>{e.confidence.replace(/_/g, " ")}</td>
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
            <h3>AI Stylometric &amp; Behavioral Analysis</h3>
            <span className="section-count">{aiAnalysis?.pairs.length ?? 0}</span>
          </div>
          <p className="muted" style={{ marginBottom: "0.75rem" }}>
            Argus compares writing and activity patterns across this actor's observed personas
            using machine-learning text/behavior similarity to identify potentially related
            identities. This is supporting intelligence only — it does not independently
            establish real-world identity, and is kept separate from the attribution confidence
            above.
          </p>
          {aiAnalysis === null ? (
            <SkeletonBlock height={120} />
          ) : aiAnalysis.status_message ? (
            <p className="muted">{aiAnalysis.status_message}</p>
          ) : (
            <div>
              <div className="signal-list" style={{ marginBottom: "1rem" }}>
                <div className="signal-row">
                  <span className="signal-label">Samples analyzed</span>
                  <span className="signal-value">
                    {aiAnalysis.personas.reduce((sum, p) => sum + p.sample_count, 0)}
                  </span>
                </div>
                <div className="signal-row">
                  <span className="signal-label">Personas compared</span>
                  <span className="signal-value">{aiAnalysis.personas.length}</span>
                </div>
                <div className="signal-row">
                  <span className="signal-label">Platforms</span>
                  <span className="signal-value">
                    {new Set(aiAnalysis.personas.map((p) => p.platform)).size}
                  </span>
                </div>
              </div>

              {aiAnalysis.pairs.map((pair, i) => (
                <div
                  key={`${pair.persona_a.username}-${pair.persona_b.username}-${i}`}
                  className="threat-category-block"
                  style={{ padding: "1rem", marginBottom: "0.75rem" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                    <strong>
                      {pair.persona_a.username} <span className="muted">({pair.persona_a.platform})</span>
                      {"  ↔  "}
                      {pair.persona_b.username} <span className="muted">({pair.persona_b.platform})</span>
                    </strong>
                  </div>

                  {pair.insufficient_data_reason ? (
                    <p className="muted">{pair.insufficient_data_reason}</p>
                  ) : (
                    <>
                      <div className="signal-list">
                        <div className="signal-row">
                          <span className="signal-label">Stylometric similarity</span>
                          <div className="signal-bar">
                            <div
                              className="signal-bar-fill"
                              style={{ width: `${(pair.stylometric_similarity ?? 0) * 100}%` }}
                            />
                          </div>
                          <span className="signal-value">
                            {((pair.stylometric_similarity ?? 0) * 100).toFixed(0)}%
                          </span>
                        </div>
                        {pair.behavioral_similarity !== null && (
                          <div className="signal-row">
                            <span className="signal-label">Behavioural similarity</span>
                            <div className="signal-bar">
                              <div
                                className="signal-bar-fill"
                                style={{ width: `${pair.behavioral_similarity * 100}%` }}
                              />
                            </div>
                            <span className="signal-value">
                              {(pair.behavioral_similarity * 100).toFixed(0)}%
                            </span>
                          </div>
                        )}
                      </div>

                      <table style={{ marginTop: "0.75rem" }}>
                        <thead>
                          <tr>
                            <th>Observed AI signal</th>
                            <th>Result</th>
                          </tr>
                        </thead>
                        <tbody>
                          {pair.signals.map((s) => (
                            <tr key={s.name}>
                              <td>{s.name}</td>
                              <td>{s.bucket}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>

                      {pair.evidence_samples.length > 0 && (
                        <table style={{ marginTop: "0.75rem" }}>
                          <thead>
                            <tr>
                              <th>Platform</th>
                              <th>Persona</th>
                              <th>Source record</th>
                              <th>Observed</th>
                            </tr>
                          </thead>
                          <tbody>
                            {pair.evidence_samples.map((e, ei) => (
                              <tr key={ei}>
                                <td>
                                  {e.platform} <Badge variant={platformBadgeVariant(e.platform)} />
                                </td>
                                <td className="mono">{e.persona_username}</td>
                                <td className="muted">{e.title ?? e.source_record_id}</td>
                                <td>
                                  {e.observed_at ? new Date(e.observed_at).toLocaleDateString() : "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </>
                  )}
                </div>
              ))}

              {aiAnalysis.method && (
                <p className="muted" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
                  Method: {aiAnalysis.method}
                </p>
              )}
              <p className="muted" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }}>
                Interpretation: AI analysis provides supporting evidence of similar writing/
                behaviour patterns. It should be evaluated together with identifiers,
                infrastructure, and other attribution evidence — not on its own.
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
