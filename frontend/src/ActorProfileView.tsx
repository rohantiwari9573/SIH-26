import { useEffect, useState } from "react";
import { ActorProfile, ApiError, downloadExport, getActorProfile } from "./api";
import ConfidenceBadge from "./ConfidenceBadge";
import GraphView from "./GraphView";
import { SkeletonBlock } from "./Skeleton";
import {
  AlertIcon,
  ArrowLeftIcon,
  DownloadIcon,
  KeyIcon,
  LoaderIcon,
  NetworkIcon,
  PenIcon,
  ServerIcon,
  UserIcon,
  WalletIcon,
} from "./icons";

const TYPE_ICON: Record<string, JSX.Element> = {
  username: <UserIcon width={13} height={13} />,
  wallet: <WalletIcon width={13} height={13} />,
  pgp_key: <KeyIcon width={13} height={13} />,
};

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
        <button className="btn-ghost" onClick={onBack}>
          <ArrowLeftIcon width={16} height={16} />
          Back to search
        </button>
        <p className="error" style={{ marginTop: "1rem" }}>
          <AlertIcon width={15} height={15} />
          {error}
        </p>
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
            last updated {new Date(profile.updated_at).toLocaleString()}
          </div>
        </div>
        <ConfidenceBadge score={profile.confidence_score} />
      </div>

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
                    <td>{ident.source_platform}</td>
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
          <GraphView actorId={actorId} />
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
