const TOKEN_STORAGE_KEY = "argus_token";

export interface ActorSearchResult {
  id: string;
  label: string;
  confidence_score: number;
  updated_at: string;
  matched_identifier?: string | null;
}

export interface IdentifierOut {
  id: string;
  identifier_type: string;
  value: string;
  source_platform: string;
  first_seen: string;
  last_seen: string;
}

export interface InfraFindingOut {
  id: string;
  onion_address: string;
  finding_type: string;
  detail: Record<string, unknown>;
  resolved_ip: string | null;
  discovered_at: string;
}

export interface StyleProfileOut {
  id: string;
  identifier_id: string;
  feature_vector: Record<string, number>;
  sample_count: number;
}

export interface AttributionEdgeOut {
  id: string;
  username_a: string;
  platform_a: string;
  username_b: string;
  platform_b: string;
  edge_type: string;
  weight: number;
}

export interface ActorProfile {
  id: string;
  label: string;
  confidence_score: number;
  created_at: string;
  updated_at: string;
  identifiers: IdentifierOut[];
  infra_findings: InfraFindingOut[];
  style_profiles: StyleProfileOut[];
  attribution_edges: AttributionEdgeOut[];
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function getToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token);
  else localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export function isLoggedIn(): boolean {
  return getToken() !== null;
}

/** FastAPI error responses are JSON like {"detail": "..."} — showing that
 * raw to the user (as this used to) renders literal braces/quotes in the UI
 * instead of a readable message. Falls back to the raw text for non-JSON
 * error bodies (e.g. a proxy/nginx error page). */
async function _extractErrorMessage(response: Response): Promise<string> {
  const body = await response.text();
  try {
    const parsed = JSON.parse(body);
    if (typeof parsed?.detail === "string") return parsed.detail;
  } catch {
    // not JSON — fall through to raw text
  }
  return body || response.statusText;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const message = await _extractErrorMessage(response);
    // A 401 on a request that DID carry a token means the token is
    // expired/invalid, not that the user typed the wrong password (that
    // case has no token attached — e.g. the login call itself). Clear the
    // stale token and bounce back to the login screen instead of leaving
    // the authenticated views showing a raw "could not validate
    // credentials" error underneath a UI that still claims to be logged in.
    if (response.status === 401 && token) {
      setToken(null);
      window.location.reload();
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export async function register(email: string, password: string): Promise<void> {
  await request("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<void> {
  const body = new URLSearchParams({ username: email, password });
  const data = await request<{ access_token: string }>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  setToken(data.access_token);
}

export function logout(): void {
  setToken(null);
}

export interface PaginatedActors {
  items: ActorSearchResult[];
  total: number;
  page: number;
  page_size: number;
}

export async function listActors(page = 1, pageSize = 100): Promise<PaginatedActors> {
  return request<PaginatedActors>(`/api/actors?page=${page}&page_size=${pageSize}`);
}

export async function searchActors(query: string): Promise<ActorSearchResult[]> {
  return request<ActorSearchResult[]>(`/api/actors/search?q=${encodeURIComponent(query)}`);
}

export async function getActorProfile(actorId: string): Promise<ActorProfile> {
  return request<ActorProfile>(`/api/actors/${actorId}`);
}

export interface PlatformBreakdownOut {
  platform: string;
  identifier_count: number;
  activity_count: number;
  first_activity: string | null;
  last_activity: string | null;
}

export interface ActorEnrichment {
  platforms: PlatformBreakdownOut[];
  total_activities: number;
  classified_activities: number;
  first_observed: string | null;
  last_observed: string | null;
  active_duration_days: number | null;
  days_since_last_observed: number | null;
  posting_frequency_per_week: number | null;
  shared_wallet_across_platforms: boolean;
  shared_pgp_key_across_platforms: boolean;
  platform_migration_order: string[];
}

export async function getActorEnrichment(actorId: string): Promise<ActorEnrichment> {
  return request<ActorEnrichment>(`/api/actors/${actorId}/enrichment`);
}

export interface GraphNode {
  type: string;
  value: string;
  source_platform: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship: string;
  weight: number;
}

export interface ActorGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  node_count: number;
  edge_count: number;
}

export interface GraphFilters {
  depth?: number;
  entityTypes?: string[]; // ENTITY_TYPE_GROUPS keys, see app/api/routes/actors.py
  relationshipTypes?: string[]; // RELATIONSHIP_TYPE_GROUPS keys
  source?: string | null; // SOURCE_FILTER_VALUES key
}

export async function getActorGraph(actorId: string, filters: GraphFilters = {}): Promise<ActorGraph> {
  const params = new URLSearchParams();
  params.set("depth", String(filters.depth ?? 1));
  if (filters.entityTypes?.length) params.set("entity_types", filters.entityTypes.join(","));
  if (filters.relationshipTypes?.length)
    params.set("relationship_types", filters.relationshipTypes.join(","));
  if (filters.source) params.set("source", filters.source);
  return request<ActorGraph>(`/api/actors/${actorId}/graph?${params.toString()}`);
}

export interface CorrelationEvidence {
  id: string;
  source: string;
  source_record_id: string;
  evidence_type: "infrastructure" | "threat_indicator" | "breach_domain";
  matched_value: string;
  description: string;
  observed_at: string | null;
  ingested_at: string;
}

export async function getActorEvidence(actorId: string): Promise<CorrelationEvidence[]> {
  return request<CorrelationEvidence[]>(`/api/actors/${actorId}/evidence`);
}

export interface ThreatActivity {
  id: string;
  actor_id: string | null;
  persona_username: string;
  source_platform: string;
  source_record_id: string;
  title: string | null;
  observed_at: string | null;
  category: string;
  category_label: string;
  classification_reason: string;
  classification_method: "source_provided" | "keyword_rule";
  classification_confidence: "high" | "medium";
}

export interface ThreatCategorySummary {
  category: string;
  category_label: string;
  activity_count: number;
  sources: string[];
}

export interface ActorThreatActivity {
  summary: ThreatCategorySummary[];
  activities: ThreatActivity[];
  activities_total: number;
  page: number;
  page_size: number;
}

/** `activities` is server-side paginated and optionally filtered to one
 * category — see the endpoint's docstring. Called with no args, it fetches
 * page 1 of ALL categories (enough to render the summary + a first page);
 * ActorProfileView re-calls with `category` set when the investigator
 * expands a specific category. */
export async function getActorThreatActivity(
  actorId: string,
  opts: { category?: string; page?: number; pageSize?: number } = {}
): Promise<ActorThreatActivity> {
  const params = new URLSearchParams();
  if (opts.category) params.set("category", opts.category);
  params.set("page", String(opts.page ?? 1));
  params.set("page_size", String(opts.pageSize ?? 50));
  return request<ActorThreatActivity>(
    `/api/actors/${actorId}/threat-activity?${params.toString()}`
  );
}

export interface AttributionSignal {
  label: string;
  value: number;
  weight: number;
  available: boolean;
}

export interface AttributionBreakdown {
  signals: AttributionSignal[];
  evidence_count: number;
  sources: string[];
}

export async function getActorAttributionBreakdown(actorId: string): Promise<AttributionBreakdown> {
  return request<AttributionBreakdown>(`/api/actors/${actorId}/attribution-breakdown`);
}

const EXPORT_FILENAMES: Record<"csv" | "json" | "report", (id: string) => string> = {
  csv: (id) => `actor_${id}.csv`,
  json: (id) => `actor_${id}.json`,
  report: (id) => `actor_${id}_report.pdf`,
};

/** Downloads an export via an authenticated request, not a plain <a href> link
 * (which can't carry the Authorization header, and putting a JWT in the URL
 * would leak it into browser history and server logs). */
export async function downloadExport(
  actorId: string,
  format: "csv" | "json" | "report"
): Promise<void> {
  const token = getToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`/api/export/${actorId}/${format}`, { headers });
  if (!response.ok) {
    const message = await _extractErrorMessage(response);
    if (response.status === 401 && token) {
      setToken(null);
      window.location.reload();
    }
    throw new ApiError(response.status, message);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = EXPORT_FILENAMES[format](actorId);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

export interface LeadInput {
  username: string;
  platform: string;
  sample_text?: string;
  wallet?: string;
  pgp_key?: string;
  onion_address?: string;
}

export interface LeadSubmitted {
  lead_id: string;
  task_id: string;
}

export async function submitLead(lead: LeadInput): Promise<LeadSubmitted> {
  return request<LeadSubmitted>("/api/leads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(lead),
  });
}

export interface JobStatus {
  task_id: string;
  status: "PENDING" | "STARTED" | "SUCCESS" | "FAILURE" | string;
  result: { actor_count: number; actors: ActorSearchResult[] } | null;
}

export async function getJobStatus(taskId: string): Promise<JobStatus> {
  return request<JobStatus>(`/api/jobs/${taskId}`);
}

export interface AnalysisJobRecord {
  id: string;
  job_type: string;
  status: string;
  target: string;
  task_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface PaginatedAnalysisJobs {
  items: AnalysisJobRecord[];
  total: number;
  page: number;
  page_size: number;
}

/** Real, persisted job history (app.models.actor.AnalysisJob) — populated
 * only for the Celery-triggered reanalyze_all path (POST /api/leads), not
 * CLI-driven ingestion. See that model's docstring. */
export async function listRecentJobs(page = 1, pageSize = 20): Promise<PaginatedAnalysisJobs> {
  return request<PaginatedAnalysisJobs>(`/api/jobs?page=${page}&page_size=${pageSize}`);
}

/** Polls a job until it reaches a terminal state (SUCCESS/FAILURE) or the
 * attempt budget runs out. Analysis is normally fast on this dataset size,
 * but there's no guarantee — bail out rather than poll forever. */
export async function waitForJob(
  taskId: string,
  { intervalMs = 1000, maxAttempts = 30 }: { intervalMs?: number; maxAttempts?: number } = {}
): Promise<JobStatus> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const status = await getJobStatus(taskId);
    if (status.status === "SUCCESS" || status.status === "FAILURE") {
      return status;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new ApiError(408, "Analysis job did not complete in time");
}

export interface StatCard {
  label: string;
  value: number;
  trend_pct: number | null;
  sparkline: number[] | null;
}

export interface DashboardStats {
  threat_actors: StatCard;
  unique_handles: StatCard;
  pgp_keys: StatCard;
  wallets_tracked: StatCard;
  attribution_links: StatCard;
  high_confidence_links: StatCard;
}

export interface TimelineEvent {
  event_type: string;
  occurred_at: string;
  summary: string;
  actor_id: string | null;
}

export interface SourceBreakdownItem {
  source_platform: string;
  count: number;
}

export interface TopLinkSignal {
  label: string;
  value: number;
  weight: number;
}

export interface TopLink {
  actor_id: string;
  actor_label: string;
  confidence: number;
  username_a: string;
  platform_a: string;
  username_b: string;
  platform_b: string;
  signals: TopLinkSignal[];
}

export interface InfraFindingRow {
  id: string;
  onion_address: string;
  finding_type: string;
  detail: Record<string, unknown>;
  resolved_ip: string | null;
  discovered_at: string;
  actor_id: string | null;
  actor_label: string | null;
}

export interface TorRelay {
  fingerprint: string;
  nickname: string;
  ip_addresses: string[];
  country: string | null;
  running: boolean;
  flags: string[];
  first_seen: string | null;
  last_seen: string | null;
}

export interface ThreatEvent {
  source: string;
  event_uuid: string;
  org_name: string | null;
  info: string;
  tags: string[];
  event_date: string | null;
  threat_level_id: number | null;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  return request<DashboardStats>("/api/dashboard/stats");
}

export async function getDashboardTimeline(limit = 20): Promise<TimelineEvent[]> {
  return request<TimelineEvent[]>(`/api/dashboard/timeline?limit=${limit}`);
}

export async function getSourceBreakdown(): Promise<SourceBreakdownItem[]> {
  return request<SourceBreakdownItem[]>("/api/dashboard/sources");
}

export async function getTopLink(): Promise<TopLink | null> {
  return request<TopLink | null>("/api/dashboard/top-link");
}

export async function getInfraFindingsGlobal(limit = 20): Promise<InfraFindingRow[]> {
  return request<InfraFindingRow[]>(`/api/dashboard/infra-findings?limit=${limit}`);
}

export async function getTorRelays(limit = 50): Promise<TorRelay[]> {
  return request<TorRelay[]>(`/api/dashboard/tor-relays?limit=${limit}`);
}

export async function getThreatEvents(limit = 50): Promise<ThreatEvent[]> {
  return request<ThreatEvent[]>(`/api/dashboard/threat-events?limit=${limit}`);
}

export interface BreachRecord {
  name: string;
  domain: string | null;
  breach_date: string | null;
  pwn_count: number;
  data_classes: string[];
  is_verified: boolean;
}

export interface DataSourceStatus {
  key: string;
  label: string;
  category: "historical" | "continuously_refreshed" | "feed" | "api";
  record_count: number;
  most_recent_at: string | null;
  configured: boolean;
}

export async function getBreachRecords(limit = 50): Promise<BreachRecord[]> {
  return request<BreachRecord[]>(`/api/dashboard/breaches?limit=${limit}`);
}

export async function getSourceRegistry(): Promise<DataSourceStatus[]> {
  return request<DataSourceStatus[]>("/api/dashboard/source-registry");
}

export interface HiddenServiceCorrelation {
  source: string;
  matched_value: string;
  description: string;
}

export interface HiddenServiceRow {
  id: string;
  onion_address: string;
  finding_type: string;
  detail: Record<string, unknown>;
  resolved_ip: string | null;
  discovered_at: string;
  actor_id: string | null;
  actor_label: string | null;
  correlations: HiddenServiceCorrelation[];
}

export interface HiddenServicesSummary {
  hidden_services: number;
  infrastructure_findings: number;
  correlations: number;
  linked_actors: number;
}

export interface HiddenServices {
  summary: HiddenServicesSummary;
  rows: HiddenServiceRow[];
}

export async function getHiddenServices(limit = 100): Promise<HiddenServices> {
  return request<HiddenServices>(`/api/dashboard/hidden-services?limit=${limit}`);
}

export interface PersonaActivityRecord {
  identifier_type: string;
  value: string;
  source_platform: string;
  actor_id: string | null;
  actor_label: string | null;
  last_seen: string;
}

export interface PersonaActivitySummary {
  total_records: number;
  unique_handles: number;
  linked_actors: number;
  pgp_keys: number;
  wallets: number;
  by_source: SourceBreakdownItem[];
}

export interface PersonaActivity {
  summary: PersonaActivitySummary;
  records: PersonaActivityRecord[];
}

export async function getIdentifierActivity(
  platforms: string[],
  limit = 200
): Promise<PersonaActivity> {
  const params = new URLSearchParams({ platforms: platforms.join(","), limit: String(limit) });
  return request<PersonaActivity>(`/api/dashboard/identifier-activity?${params.toString()}`);
}

export interface Alert {
  alert_type: "high_confidence_actor" | "new_linkage" | "correlation" | "infra_finding";
  severity: "high" | "medium" | "low";
  summary: string;
  occurred_at: string;
  actor_id: string | null;
}

export async function getAlerts(limit = 30): Promise<Alert[]> {
  return request<Alert[]>(`/api/dashboard/alerts?limit=${limit}`);
}

export interface ComponentStatus {
  name: string;
  healthy: boolean;
  detail: string | null;
}

export interface SystemStatus {
  checked_at: string;
  components: ComponentStatus[];
}

export async function getSystemStatus(): Promise<SystemStatus> {
  return request<SystemStatus>("/api/dashboard/system-status");
}

export { ApiError };
