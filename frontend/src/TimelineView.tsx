import { useEffect, useState } from "react";
import { TimelineEvent, TimelineFilters, getDashboardTimeline } from "./api";
import { SkeletonRows } from "./Skeleton";

const EVENT_LABELS: Record<string, string> = {
  actor_created: "Actor derived",
  infra_finding: "Infrastructure finding",
  lead_submitted: "Lead submitted",
  threat_activity: "Threat activity",
};

// Mirrors app.services.threat_categorization.CATEGORY_LABELS — kept in sync
// by hand (small, stable taxonomy); the "" entry means "no category filter".
const CATEGORY_OPTIONS: [string, string][] = [
  ["", "All categories"],
  ["credential_data_theft", "Credential / Data Theft"],
  ["hacking_services", "Hacking Services"],
  ["malware", "Malware"],
  ["financial_fraud", "Financial Fraud"],
  ["money_laundering", "Money Laundering"],
  ["drug_trafficking", "Drug Trafficking"],
  ["weapons_arms", "Weapons / Arms"],
  ["stolen_data", "Stolen Data"],
  ["other_cybercrime", "Other Cybercrime"],
];

const EVENT_TYPE_OPTIONS: [string, string][] = [
  ["", "All event types"],
  ["actor_created", "Actor derived"],
  ["infra_finding", "Infrastructure finding"],
  ["lead_submitted", "Lead submitted"],
  ["threat_activity", "Threat activity"],
];

export default function TimelineView({ onSelectActor }: { onSelectActor: (id: string) => void }) {
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [source, setSource] = useState("");
  const [category, setCategory] = useState("");
  const [eventType, setEventType] = useState("");

  const filters: TimelineFilters = {
    startDate: startDate || undefined,
    endDate: endDate || undefined,
    source: source || undefined,
    category: category || undefined,
    eventType: eventType || undefined,
  };
  const hasActiveFilter = Object.values(filters).some(Boolean);

  useEffect(() => {
    setEvents(null);
    getDashboardTimeline(200, filters)
      .then(setEvents)
      .catch(() => setEvents([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startDate, endDate, source, category, eventType]);

  function clearFilters() {
    setStartDate("");
    setEndDate("");
    setSource("");
    setCategory("");
    setEventType("");
  }

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>Timeline Explorer</h2>
        <p className="muted">
          Real, timestamped rows from Argus's own database — query by date range, source
          platform, threat category, or event type to answer "what did this happen, and when."
        </p>
      </div>

      <div className="section-card" style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.8rem" }}>
            From
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.8rem" }}>
            To
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.8rem" }}>
            Source / platform
            <input
              type="text"
              placeholder="e.g. mock_marketplace_1"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              style={{ minWidth: 200 }}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.8rem" }}>
            Category
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORY_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.8rem" }}>
            Event type
            <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
              {EVENT_TYPE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {hasActiveFilter && (
            <button className="btn-ghost" onClick={clearFilters} style={{ alignSelf: "flex-end" }}>
              Clear filters
            </button>
          )}
        </div>
      </div>

      <div className="section-card">
        {events === null ? (
          <SkeletonRows count={8} />
        ) : events.length === 0 ? (
          <p className="muted">
            {hasActiveFilter ? "No events match the current filters." : "No activity recorded yet."}
          </p>
        ) : (
          <ul className="timeline-list">
            {events.map((e, i) => (
              <li
                key={i}
                onClick={() => e.actor_id && onSelectActor(e.actor_id)}
                style={{ cursor: e.actor_id ? "pointer" : "default" }}
              >
                <span className="timeline-dot" />
                <div>
                  <div>
                    <span className="type-pill" style={{ marginRight: "0.5rem" }}>
                      {EVENT_LABELS[e.event_type] ?? e.event_type}
                    </span>
                    {e.summary}
                    {e.source && <span className="muted"> — {e.source}</span>}
                  </div>
                  <div className="muted" style={{ fontSize: "0.8rem" }}>
                    {new Date(e.occurred_at).toLocaleString()}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
