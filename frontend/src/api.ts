const TOKEN_STORAGE_KEY = "sih26151_token";

export interface ActorSearchResult {
  id: string;
  label: string;
  confidence_score: number;
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

export interface ActorProfile {
  id: string;
  label: string;
  confidence_score: number;
  created_at: string;
  updated_at: string;
  identifiers: IdentifierOut[];
  infra_findings: InfraFindingOut[];
  style_profiles: StyleProfileOut[];
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

export async function listActors(): Promise<ActorSearchResult[]> {
  return request<ActorSearchResult[]>("/api/actors");
}

export async function searchActors(query: string): Promise<ActorSearchResult[]> {
  return request<ActorSearchResult[]>(`/api/actors/search?q=${encodeURIComponent(query)}`);
}

export async function getActorProfile(actorId: string): Promise<ActorProfile> {
  return request<ActorProfile>(`/api/actors/${actorId}`);
}

export interface GraphNode {
  type: string;
  value: string;
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
}

export async function getActorGraph(actorId: string): Promise<ActorGraph> {
  return request<ActorGraph>(`/api/actors/${actorId}/graph`);
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

export { ApiError };
