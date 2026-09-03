import { useSyncExternalStore } from "react";
import { ActorSearchResult } from "./api";
import Badge from "./Badge";
import { AlertIcon, LoaderIcon, PlayIcon } from "./icons";
import { USERNAME_A, USERNAME_B, getSnapshot, resetDemo, runDemo, subscribe } from "./demoScenarioStore";

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
  // Reads from demoScenarioStore rather than local state — the run itself
  // lives in that module-level store precisely so it keeps going (and is
  // still there to reattach to) if this component unmounts mid-run because
  // the investigator switched to a different page and came back.
  const { steps, running, error, beforeA, beforeB, afterA, afterB, resultActorId } =
    useSyncExternalStore(subscribe, getSnapshot);

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
