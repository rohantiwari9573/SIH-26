import { FormEvent, useState } from "react";
import { ApiError, submitLead, waitForJob } from "./api";

type Status = "idle" | "submitting" | "analyzing" | "done" | "error";

export default function SubmitLeadView({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [platform, setPlatform] = useState("");
  const [sampleText, setSampleText] = useState("");
  const [wallet, setWallet] = useState("");
  const [pgpKey, setPgpKey] = useState("");
  const [onionAddress, setOnionAddress] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [resultCount, setResultCount] = useState<number | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setStatus("submitting");
    try {
      const { task_id } = await submitLead({
        username,
        platform,
        sample_text: sampleText || undefined,
        wallet: wallet || undefined,
        pgp_key: pgpKey || undefined,
        onion_address: onionAddress || undefined,
      });
      setStatus("analyzing");
      const job = await waitForJob(task_id);
      if (job.status === "FAILURE") {
        throw new ApiError(500, "Analysis job failed");
      }
      setResultCount(job.result?.actor_count ?? null);
      setStatus("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Submission failed");
      setStatus("error");
    }
  }

  if (status === "done") {
    return (
      <div className="card" style={{ width: "auto", maxWidth: 480 }}>
        <h2>Lead analyzed</h2>
        <p className="muted">
          The pipeline re-ran against this lead plus everything already known.
          {resultCount !== null && ` ${resultCount} actor cluster(s) now exist.`}
        </p>
        <button onClick={onDone}>Back to search</button>
      </div>
    );
  }

  const busy = status === "submitting" || status === "analyzing";

  return (
    <form className="card" style={{ width: "auto", maxWidth: 480 }} onSubmit={handleSubmit}>
      <h2>Submit a new lead</h2>
      <p className="muted">
        Feeds one newly-collected persona into the pipeline and re-runs full
        attribution against it plus every existing lead.
      </p>

      <label>
        Username *
        <input required value={username} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <label>
        Platform *
        <input required value={platform} onChange={(e) => setPlatform(e.target.value)} />
      </label>
      <label>
        Writing sample (for stylometric matching)
        <textarea
          rows={4}
          value={sampleText}
          onChange={(e) => setSampleText(e.target.value)}
          style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "0.5rem",
            color: "var(--text)",
            fontSize: "0.9rem",
            fontFamily: "inherit",
          }}
        />
      </label>
      <label>
        Wallet address
        <input value={wallet} onChange={(e) => setWallet(e.target.value)} />
      </label>
      <label>
        PGP key fingerprint
        <input value={pgpKey} onChange={(e) => setPgpKey(e.target.value)} />
      </label>
      <label>
        Onion address (if an infra leak already confirmed it)
        <input value={onionAddress} onChange={(e) => setOnionAddress(e.target.value)} />
      </label>

      {error && <p className="error">{error}</p>}

      <button type="submit" disabled={busy}>
        {status === "submitting" && "Submitting..."}
        {status === "analyzing" && "Analyzing..."}
        {!busy && "Submit lead"}
      </button>
      <button type="button" className="link-button" onClick={onDone} disabled={busy}>
        Cancel
      </button>
    </form>
  );
}
