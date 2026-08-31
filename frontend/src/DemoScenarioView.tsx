import { useState } from "react";
import { ActorSearchResult, ApiError, searchActors, submitLead, waitForJob } from "./api";
import Badge from "./Badge";
import { AlertIcon, LoaderIcon, PlayIcon } from "./icons";

/** Two dedicated, obviously-synthetic personas that exist ONLY for this
 * demo — never reused by the real seed dataset, so running/resetting this
 * never touches organic actor data or its confidence numbers. Everything
 * below goes through the real POST /api/leads -> Celery -> run_full_analysis
 * pipeline (app.services.pipeline) exactly like a real investigator
 * submission — nothing here talks to Postgres or Neo4j directly. */
const DEMO_PLATFORM = "argus_controlled_demo";
const USERNAME_A = "demo_actor_alpha";
const USERNAME_B = "demo_actor_beta";
const WALLET_A = "DEMO-WALLET-ALPHA-0001";
const WALLET_B_BASELINE = "DEMO-WALLET-BETA-0002";

type StepStatus = "pending" | "active" | "done" | "error";
interface Step {
  label: string;
  status: StepStatus;
}

const PIPELINE_STEPS = [
  "Submit Lead (POST /api/leads)",
  "PostgreSQL (RawPersona upserted)",
  "Celery Job (reanalyze_all)",
  "Analysis (run_full_analysis)",
  "Neo4j Relationship (MATCH/MERGE)",
  "Attribution Update (confidence recomputed)",
];

function ActorSummary({ label, actor }: { label: string; actor: ActorSearchResult | null }) {
  return (
    <div className="section-card" style={{ flex: 1 }}>
      <div className="muted" style={{ fontSize: "0.8rem", marginBottom: "0.3rem" }}>
        {label}
      </div>
      {actor ? (
        <>
          <div style={{ fontWeight: 600 }}>{actor.label}</div>
          <div className="muted" style={{ fontSize: "0.85rem" }}>
            Confidence: {(actor.confidence_score * 100).toFixed(0)}%
          </div>
        </>
      ) : (
        <div className="muted">—</div>
      )}
    </div>
  );
}

export default function DemoScenarioView({
  onSelectActor,
}: {
  onSelectActor: (id: string) => void;
}) {
  const [steps, setSteps] = useState<Step[]>(
    PIPELINE_STEPS.map((label) => ({ label, status: "pending" }))
  );
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [beforeA, setBeforeA] = useState<ActorSearchResult | null>(null);
  const [beforeB, setBeforeB] = useState<ActorSearchResult | null>(null);
  const [afterA, setAfterA] = useState<ActorSearchResult | null>(null);
  const [afterB, setAfterB] = useState<ActorSearchResult | null>(null);
  const [resultActorId, setResultActorId] = useState<string | null>(null);

  function setStepStatus(index: number, status: StepStatus) {
    setSteps((prev) => prev.map((s, i) => (i === index ? { ...s, status } : s)));
  }

  async function lookupOne(username: string): Promise<ActorSearchResult | null> {
    const results = await searchActors(username);
    return results.find((r) => r.matched_identifier === username) ?? results[0] ?? null;
  }

  async function runDemo() {
    setRunning(true);
    setError(null);
    setSteps(PIPELINE_STEPS.map((label) => ({ label, status: "pending" })));
    setAfterA(null);
    setAfterB(null);
    setResultActorId(null);

    try {
      // Baseline: both personas exist with DIFFERENT wallets — no shared identifier.
      setStepStatus(0, "active");
      const leadA = await submitLead({ username: USERNAME_A, platform: DEMO_PLATFORM, wallet: WALLET_A });
      setStepStatus(0, "done");
      setStepStatus(1, "active");
      await waitForJob(leadA.task_id);
      setStepStatus(1, "done");

      const leadB1 = await submitLead({
        username: USERNAME_B,
        platform: DEMO_PLATFORM,
        wallet: WALLET_B_BASELINE,
      });
      setStepStatus(2, "active");
      await waitForJob(leadB1.task_id);
      setStepStatus(2, "done");

      const [bA, bB] = await Promise.all([lookupOne(USERNAME_A), lookupOne(USERNAME_B)]);
      setBeforeA(bA);
      setBeforeB(bB);

      // New evidence: demo_actor_beta now shares demo_actor_alpha's wallet.
      setStepStatus(3, "active");
      const leadB2 = await submitLead({
        username: USERNAME_B,
        platform: DEMO_PLATFORM,
        wallet: WALLET_A,
      });
      setStepStatus(3, "done");
      setStepStatus(4, "active");
      const job = await waitForJob(leadB2.task_id);
      setStepStatus(4, "done");
      setStepStatus(5, "active");

      const [aA, aB] = await Promise.all([lookupOne(USERNAME_A), lookupOne(USERNAME_B)]);
      setAfterA(aA);
      setAfterB(aB);
      setStepStatus(5, "done");
      if (aA && aB && aA.id === aB.id) setResultActorId(aA.id);

      void job; // result already reflected via lookupOne above
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Demo run failed");
      setSteps((prev) => prev.map((s) => (s.status === "active" ? { ...s, status: "error" } : s)));
    } finally {
      setRunning(false);
    }
  }

  async function resetDemo() {
    setRunning(true);
    setError(null);
    try {
      const lead = await submitLead({
        username: USERNAME_B,
        platform: DEMO_PLATFORM,
        wallet: WALLET_B_BASELINE,
      });
      await waitForJob(lead.task_id);
      setAfterA(null);
      setAfterB(null);
      setResultActorId(null);
      const [bA, bB] = await Promise.all([lookupOne(USERNAME_A), lookupOne(USERNAME_B)]);
      setBeforeA(bA);
      setBeforeB(bB);
      setSteps(PIPELINE_STEPS.map((label) => ({ label, status: "pending" })));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed");
    } finally {
      setRunning(false);
    }
  }

  const merged = Boolean(resultActorId);

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h2>Controlled Demonstration</h2>
        <p className="muted">
          Demonstrates how new evidence changes actor attribution, end to end, using Argus's real
          pipeline — the same POST /api/leads, Celery, and Neo4j path a real investigator
          submission uses. Nothing here bypasses the application or writes to the database
          directly.
        </p>
        <Badge variant="synthetic" label="Synthetic / Controlled Environment" />
      </div>

      <div className="section-card" style={{ marginBottom: "1.5rem" }}>
        <div className="section-heading">
          <PlayIcon width={16} height={16} />
          <h3>Run Wallet Correlation Demo</h3>
        </div>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          Two synthetic personas ({USERNAME_A} / {USERNAME_B}) start with independent wallets.
          Running the demo submits a real lead giving {USERNAME_B} {USERNAME_A}'s wallet, and
          shows the resulting pipeline run and attribution change.
        </p>
        <div style={{ display: "flex", gap: "0.6rem", marginBottom: "1rem" }}>
          <button onClick={runDemo} disabled={running}>
            {running ? <LoaderIcon width={15} height={15} /> : <PlayIcon width={15} height={15} />}
            {running ? "Running..." : "Run Wallet Correlation Demo"}
          </button>
          {(beforeA || afterA) && (
            <button className="btn-ghost" onClick={resetDemo} disabled={running}>
              Reset Demo
            </button>
          )}
        </div>

        {error && (
          <p className="error" style={{ marginBottom: "1rem" }}>
            <AlertIcon width={15} height={15} />
            {error}
          </p>
        )}

        <ul className="timeline-list">
          {steps.map((s, i) => (
            <li key={i}>
              <span
                className="timeline-dot"
                style={{
                  background:
                    s.status === "done"
                      ? "var(--high)"
                      : s.status === "active"
                      ? "var(--accent)"
                      : s.status === "error"
                      ? "var(--danger)"
                      : "var(--low)",
                }}
              />
              <div>{s.label}</div>
            </li>
          ))}
        </ul>
      </div>

      {(beforeA || beforeB) && (
        <div className="section-card" style={{ marginBottom: "1.5rem" }}>
          <div className="section-heading">
            <h3>Before</h3>
          </div>
          <div style={{ display: "flex", gap: "1rem" }}>
            <ActorSummary label={USERNAME_A} actor={beforeA} />
            <ActorSummary label={USERNAME_B} actor={beforeB} />
          </div>
          <p className="muted" style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}>
            {beforeA && beforeB && beforeA.id === beforeB.id
              ? "Already linked — run Reset Demo to restore the independent baseline first."
              : "No connection — independent identifiers, independent actors."}
          </p>
        </div>
      )}

      {(afterA || afterB) && (
        <div className="section-card">
          <div className="section-heading">
            <h3>After</h3>
          </div>
          <div style={{ display: "flex", gap: "1rem" }}>
            <ActorSummary label={USERNAME_A} actor={afterA} />
            <ActorSummary label={USERNAME_B} actor={afterB} />
          </div>
          <p className="muted" style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}>
            {merged
              ? "Both personas now resolve to the same actor — attribution was recomputed from the newly submitted evidence, not hardcoded."
              : "Personas did not merge (unexpected) — check the pipeline log above."}
          </p>
          {merged && resultActorId && (
            <button className="btn-secondary" style={{ marginTop: "0.75rem" }} onClick={() => onSelectActor(resultActorId)}>
              View merged actor profile &rarr;
            </button>
          )}
        </div>
      )}
    </div>
  );
}
