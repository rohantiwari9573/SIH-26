import { useEffect, useRef, useState } from "react";
import { ActorSearchResult, ApiError, downloadExport, listActors } from "./api";
import ConfidenceBadge from "./ConfidenceBadge";
import { SkeletonRows } from "./Skeleton";
import { AlertIcon, CheckIcon, ClipboardIcon, DownloadIcon, LoaderIcon } from "./icons";

// How long the "Downloaded" checkmark stays up before a button reverts to
// its normal label. The export itself often resolves in well under a
// second (csv/json are just DB rows), so without this the loading spinner
// flashes and disappears too fast to register — the download happens
// silently in the background and it looks like the button did nothing.
const DOWNLOADED_FLASH_MS = 1800;

// PS-26151 "analytical output / export" requirement. Purely a UI around
// Argus's existing export pipeline (GET /api/export/{id}/csv|json|report) —
// no new report-generation backend, no duplicated logic.
export default function ReportsView({ onSelectActor }: { onSelectActor: (id: string) => void }) {
  const [actors, setActors] = useState<ActorSearchResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [exporting, setExporting] = useState<string | null>(null); // `${actorId}:${format}`
  const [downloaded, setDownloaded] = useState<string | null>(null); // `${actorId}:${format}`
  const [exportError, setExportError] = useState<string | null>(null);
  const [selectedActorId, setSelectedActorId] = useState<string>("");
  const downloadedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (downloadedTimer.current) clearTimeout(downloadedTimer.current);
    };
  }, []);

  useEffect(() => {
    setError(null);
    listActors(1, 200)
      .then((r) => setActors(r.items))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load actors"));
  }, [retryToken]);

  async function handleExport(actorId: string, format: "csv" | "json" | "report") {
    setExportError(null);
    const key = `${actorId}:${format}`;
    setExporting(key);
    try {
      await downloadExport(actorId, format);
      if (downloadedTimer.current) clearTimeout(downloadedTimer.current);
      setDownloaded(key);
      downloadedTimer.current = setTimeout(() => setDownloaded(null), DOWNLOADED_FLASH_MS);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : "Export failed");
    } finally {
      setExporting(null);
    }
  }

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>Reports</h2>
        <p className="muted">
          Investigation-ready output for any actor — attribution breakdown, evidence, provenance,
          and infrastructure findings, exported via Argus's existing CSV / JSON / PDF report
          pipeline.
        </p>
      </div>

      {error && (
        <p className="error" style={{ marginBottom: "1.5rem" }}>
          <AlertIcon width={15} height={15} />
          {error}
          <button className="btn-ghost" style={{ marginLeft: "0.75rem" }} onClick={() => setRetryToken((t) => t + 1)}>
            Retry
          </button>
        </p>
      )}

      {!error && (
        <>
          <div className="section-card" style={{ marginBottom: "1.5rem" }}>
            <div className="section-heading">
              <ClipboardIcon width={16} height={16} />
              <h3>Generate Investigation Report</h3>
            </div>
            <p className="muted" style={{ marginBottom: "0.75rem" }}>
              Includes attribution evidence, infrastructure intelligence, correlation evidence,
              and source provenance for the selected actor.
            </p>
            <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
              <select
                value={selectedActorId}
                onChange={(e) => setSelectedActorId(e.target.value)}
                style={{ minWidth: 260 }}
              >
                <option value="">Select an actor...</option>
                {(actors ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </select>
              <button
                className="btn-secondary"
                disabled={!selectedActorId || exporting !== null}
                onClick={() => handleExport(selectedActorId, "report")}
              >
                {exporting === `${selectedActorId}:report` ? (
                  <LoaderIcon width={15} height={15} />
                ) : downloaded === `${selectedActorId}:report` ? (
                  <CheckIcon width={15} height={15} />
                ) : (
                  <DownloadIcon width={15} height={15} />
                )}
                {downloaded === `${selectedActorId}:report` ? "Downloaded" : "Generate PDF Report"}
              </button>
            </div>
          </div>

          {exportError && (
            <p className="error" style={{ marginBottom: "1.5rem" }}>
              <AlertIcon width={15} height={15} />
              {exportError}
            </p>
          )}

          <div className="section-card">
            <div className="section-heading">
              <h3>Actor Reports</h3>
              {actors && <span className="section-count">{actors.length}</span>}
            </div>

            {actors === null ? (
              <SkeletonRows count={5} />
            ) : actors.length === 0 ? (
              <p className="muted">No actors derived yet — submit a lead to run attribution.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Actor</th>
                    <th>Attribution Confidence</th>
                    <th>Last Updated</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {actors.map((a) => (
                    <tr key={a.id}>
                      <td onClick={() => onSelectActor(a.id)} style={{ cursor: "pointer" }}>
                        {a.label}
                      </td>
                      <td>
                        <ConfidenceBadge score={a.confidence_score} />
                      </td>
                      <td>{new Date(a.updated_at).toLocaleString()}</td>
                      <td>
                        <div style={{ display: "flex", gap: "0.4rem" }}>
                          {(["csv", "json", "report"] as const).map((format) => {
                            const key = `${a.id}:${format}`;
                            return (
                              <button
                                key={format}
                                className="btn-ghost"
                                style={{ padding: "0.3rem 0.55rem", fontSize: "0.78rem" }}
                                disabled={exporting !== null}
                                onClick={() => handleExport(a.id, format)}
                              >
                                {exporting === key ? (
                                  <LoaderIcon width={13} height={13} />
                                ) : downloaded === key ? (
                                  <CheckIcon width={13} height={13} />
                                ) : (
                                  format.toUpperCase()
                                )}
                              </button>
                            );
                          })}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
