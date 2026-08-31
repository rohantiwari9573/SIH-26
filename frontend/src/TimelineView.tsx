import { useEffect, useState } from "react";
import { TimelineEvent, getDashboardTimeline } from "./api";
import { SkeletonRows } from "./Skeleton";

const EVENT_LABELS: Record<string, string> = {
  actor_created: "Actor derived",
  infra_finding: "Infrastructure finding",
  lead_submitted: "Lead submitted",
  threat_activity: "Threat activity",
};

export default function TimelineView({ onSelectActor }: { onSelectActor: (id: string) => void }) {
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);

  useEffect(() => {
    getDashboardTimeline(100).then(setEvents).catch(() => setEvents([]));
  }, []);

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>Timeline Explorer</h2>
        <p className="muted">
          Every event below is a real timestamped row from Argus's own database — actor
          derivations, infrastructure findings, and submitted leads, in observation order.
        </p>
      </div>
      <div className="section-card">
        {events === null ? (
          <SkeletonRows count={8} />
        ) : events.length === 0 ? (
          <p className="muted">No activity recorded yet.</p>
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
