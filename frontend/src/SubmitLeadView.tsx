import { FormEvent, useState } from "react";
import { ApiError, submitLead, waitForJob } from "./api";
import { AlertIcon, EyeIcon, LoaderIcon, PlusIcon } from "./icons";

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
      <div className="panel" style={{ maxWidth: 480, margin: "2rem auto" }}>
        <div
          className="brand-mark"
          style={{ width: 40, height: 40, borderRadius: 10, marginBottom: "1rem" }}
        >
          <EyeIcon width={20} height={20} />
        </div>
        <h2 style={{ marginBottom: "0.5rem" }}>Lead analyzed</h2>
        <p className="muted" style={{ marginBottom: "1.25rem" }}>
          The pipeline re-ran against this lead plus everything already known.
          {resultCount !== null && ` ${resultCount} actor cluster(s) now exist.`}
        </p>
        <button onClick={onDone}>Back to search</button>
      </div>
    );
  }

  const busy = status === "submitting" || status === "analyzing";

  return (
    <form
      className="panel"
      style={{ maxWidth: 520, margin: "0 auto", display: "flex", flexDirection: "column", gap: "1.1rem" }}
      onSubmit={handleSubmit}
    >
      <div>
        <h2 style={{ fontSize: "1.15rem", marginBottom: "0.35rem" }}>Submit a new lead</h2>
        <p className="muted">
          Feeds one newly-collected persona into the pipeline and re-runs full attribution
          against it plus every existing lead.
        </p>
      </div>

      <label>
        Username <span className="field-hint">required</span>
        <input required value={username} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <label>
        Platform <span className="field-hint">required</span>
        <input required value={platform} onChange={(e) => setPlatform(e.target.value)} />
      </label>
      <label>
        Writing sample <span className="field-hint">for stylometric matching</span>
        <textarea rows={4} value={sampleText} onChange={(e) => setSampleText(e.target.value)} />
      </label>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        <label>
          Wallet address
          <input value={wallet} onChange={(e) => setWallet(e.target.value)} />
        </label>
        <label>
          PGP key fingerprint
          <input value={pgpKey} onChange={(e) => setPgpKey(e.target.value)} />
        </label>
      </div>
      <label>
        Onion address <span className="field-hint">if an infra leak already confirmed it</span>
        <input value={onionAddress} onChange={(e) => setOnionAddress(e.target.value)} />
      </label>

      {error && (
        <p className="error">
          <AlertIcon width={15} height={15} />
          {error}
        </p>
      )}

      <div style={{ display: "flex", gap: "0.6rem" }}>
        <button type="submit" disabled={busy}>
          {busy ? <LoaderIcon width={15} height={15} /> : <PlusIcon width={15} height={15} />}
          {status === "submitting" && "Submitting..."}
          {status === "analyzing" && "Analyzing..."}
          {!busy && "Submit lead"}
        </button>
        <button type="button" className="btn-ghost" onClick={onDone} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}
