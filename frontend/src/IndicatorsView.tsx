import { useEffect, useState } from "react";
import { ThreatEvent, getThreatEvents } from "./api";
import { SkeletonRows } from "./Skeleton";

export default function IndicatorsView() {
  const [events, setEvents] = useState<ThreatEvent[] | null>(null);

  useEffect(() => {
    getThreatEvents(100).then(setEvents).catch(() => setEvents([]));
  }, []);

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>Threat Indicators</h2>
        <p className="muted">
          Real event metadata from public MISP-format OSINT feeds (CIRCL and botvrij.eu). A feed
          entry is not proof any specific actor owns or controls what it describes — treat as
          independent corroborating context only.
        </p>
      </div>
      <div className="section-card">
        {events === null ? (
          <SkeletonRows count={6} />
        ) : events.length === 0 ? (
          <p className="muted">
            No indicator data ingested yet — run <code>scripts/ingest_misp_osint.py</code>.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Event</th>
                <th>Feed</th>
                <th>Org</th>
                <th>Date</th>
                <th>Tags</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.event_uuid}>
                  <td>{e.info}</td>
                  <td>{e.source === "misp_botvrij_osint" ? "botvrij.eu" : "CIRCL"}</td>
                  <td>{e.org_name ?? "—"}</td>
                  <td>{e.event_date ?? "—"}</td>
                  <td>
                    {e.tags
                      .filter((t) => !t.startsWith("misp:"))
                      .slice(0, 3)
                      .join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
