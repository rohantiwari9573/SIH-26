import { useEffect, useState } from "react";
import { TorRelay, getTorRelays } from "./api";
import { SkeletonRows } from "./Skeleton";

export default function InfrastructureView() {
  const [relays, setRelays] = useState<TorRelay[] | null>(null);

  useEffect(() => {
    getTorRelays(100).then(setRelays).catch(() => setRelays([]));
  }, []);

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>Tor Infrastructure</h2>
        <p className="muted">
          Live relay metadata from the Tor Project's public Onionoo API. Relay operators are
          not dark-web hidden-service operators — this is network/infrastructure intelligence,
          not actor attribution.
        </p>
      </div>
      <div className="section-card">
        {relays === null ? (
          <SkeletonRows count={6} />
        ) : relays.length === 0 ? (
          <p className="muted">
            No relay data ingested yet — run <code>scripts/ingest_onionoo.py</code>.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Nickname</th>
                <th>Fingerprint</th>
                <th>Country</th>
                <th>IP Address(es)</th>
                <th>Flags</th>
                <th>Running</th>
                <th>Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {relays.map((r) => (
                <tr key={r.fingerprint}>
                  <td>{r.nickname}</td>
                  <td className="mono">{r.fingerprint.slice(0, 12)}…</td>
                  <td>{r.country?.toUpperCase() ?? "—"}</td>
                  <td className="mono">{r.ip_addresses[0] ?? "—"}</td>
                  <td>{r.flags.slice(0, 3).join(", ")}</td>
                  <td>{r.running ? "Yes" : "No"}</td>
                  <td>{r.last_seen ? new Date(r.last_seen).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
