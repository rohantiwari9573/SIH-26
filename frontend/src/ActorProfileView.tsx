import { useEffect, useState } from "react";
import { ActorProfile, ApiError, downloadExport, getActorProfile } from "./api";
import ConfidenceBadge from "./ConfidenceBadge";
import GraphView from "./GraphView";

export default function ActorProfileView({
  actorId,
  onBack,
}: {
  actorId: string;
  onBack: () => void;
}) {
  const [profile, setProfile] = useState<ActorProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);

  useEffect(() => {
    getActorProfile(actorId)
      .then(setProfile)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load actor"));
  }, [actorId]);

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
        <button onClick={onBack}>&larr; Back to search</button>
        <p className="error">{error}</p>
      </div>
    );
  }

  if (!profile) {
    return <p className="muted">Loading actor profile...</p>;
  }

  return (
    <div>
      <button onClick={onBack}>&larr; Back to search</button>

      <div className="profile-header">
        <h2>{profile.label}</h2>
        <ConfidenceBadge score={profile.confidence_score} />
      </div>

      <div className="export-bar">
        {(["csv", "json", "report"] as const).map((format) => (
          <button
            key={format}
            onClick={() => handleExport(format)}
            disabled={exporting !== null}
          >
            {exporting === format ? "Exporting..." : `Export ${format.toUpperCase()}`}
          </button>
        ))}
      </div>
      {exportError && <p className="error">{exportError}</p>}

      <section>
        <h3>Identifiers</h3>
        {profile.identifiers.length === 0 && <p className="muted">None recorded.</p>}
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
                <td>{ident.identifier_type}</td>
                <td className="mono">{ident.value}</td>
                <td>{ident.source_platform}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3>Infrastructure findings</h3>
        {profile.infra_findings.length === 0 && <p className="muted">None recorded.</p>}
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
      </section>

      <section>
        <h3>Relationship graph</h3>
        <GraphView actorId={actorId} />
      </section>

      <section>
        <h3>Style profiles</h3>
        {profile.style_profiles.length === 0 && <p className="muted">None recorded.</p>}
        <p className="muted">
          {profile.style_profiles.length} stylometric sample(s) contributed to the
          behavioral-analysis signal for this actor.
        </p>
      </section>
    </div>
  );
}
