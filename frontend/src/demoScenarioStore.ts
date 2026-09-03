import { ActorSearchResult, ApiError, searchActors, submitLead, waitForJob } from "./api";

/** Runs the Controlled Demo's pipeline outside of DemoScenarioView's own
 * component state, specifically so the run survives the component
 * unmounting. Argus has no URL routing (App.tsx renders one view at a
 * time from in-memory state — see the View union there), so navigating to
 * any other page unmounts DemoScenarioView entirely; state that lived in
 * useState there was reset to its initial value on remount even though the
 * actual submitted lead/Celery job kept running server-side the whole
 * time. This module-level store is a plain subscribe/getSnapshot pair
 * (consumed via useSyncExternalStore) so the run keeps going regardless of
 * whether anything is mounted to look at it, and reopening the demo page
 * mid-run just reattaches to whatever is already in progress. */

const DEMO_PLATFORM = "argus_controlled_demo";
export const USERNAME_A = "demo_actor_alpha";
export const USERNAME_B = "demo_actor_beta";
const WALLET_A = "DEMO-WALLET-ALPHA-0001";
const WALLET_B_BASELINE = "DEMO-WALLET-BETA-0002";

export type StepStatus = "pending" | "active" | "done" | "error";
export interface Step {
  label: string;
  status: StepStatus;
}

export const PIPELINE_STEPS = [
  "Submit Lead (POST /api/leads)",
  "PostgreSQL (RawPersona upserted)",
  "Celery Job (reanalyze_all)",
  "Analysis (run_full_analysis)",
  "Neo4j Relationship (MATCH/MERGE)",
  "Attribution Update (confidence recomputed)",
];

interface DemoState {
  steps: Step[];
  running: boolean;
  error: string | null;
  beforeA: ActorSearchResult | null;
  beforeB: ActorSearchResult | null;
  afterA: ActorSearchResult | null;
  afterB: ActorSearchResult | null;
  resultActorId: string | null;
}

function initialSteps(): Step[] {
  return PIPELINE_STEPS.map((label) => ({ label, status: "pending" as StepStatus }));
}

let state: DemoState = {
  steps: initialSteps(),
  running: false,
  error: null,
  beforeA: null,
  beforeB: null,
  afterA: null,
  afterB: null,
  resultActorId: null,
};

const listeners = new Set<() => void>();

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getSnapshot(): DemoState {
  return state;
}

function setState(patch: Partial<DemoState>) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}

function setStepStatus(index: number, status: StepStatus) {
  setState({ steps: state.steps.map((s, i) => (i === index ? { ...s, status } : s)) });
}

async function lookupOne(username: string): Promise<ActorSearchResult | null> {
  const results = await searchActors(username);
  return results.find((r) => r.matched_identifier === username) ?? results[0] ?? null;
}

export async function runDemo() {
  if (state.running) return;
  setState({ running: true, error: null, steps: initialSteps(), afterA: null, afterB: null, resultActorId: null });

  try {
    // Baseline: both personas exist with DIFFERENT wallets — no shared identifier.
    // Submitted sequentially, not in parallel: run_full_analysis rebuilds
    // the derived actor/attribution tables from scratch on every run, so
    // two overlapping runs would both be writing that rebuild against the
    // same tables at once — a real correctness risk, not just a perf one.
    // (Tried running them concurrently; it didn't even help — both runs
    // just contend for the same DB/CPU and end up taking about as long
    // as one sequential pair does anyway.)
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

    // Captured now (this is genuinely the pre-merge state) but not shown
    // yet — setting it here would render the Before panel while the merge
    // below is still running, making it look like a separate, premature
    // result instead of one half of a single before/after comparison.
    const [bA, bB] = await Promise.all([lookupOne(USERNAME_A), lookupOne(USERNAME_B)]);

    // New evidence: demo_actor_beta now shares demo_actor_alpha's wallet.
    setStepStatus(3, "active");
    const leadB2 = await submitLead({
      username: USERNAME_B,
      platform: DEMO_PLATFORM,
      wallet: WALLET_A,
    });
    setStepStatus(3, "done");
    setStepStatus(4, "active");
    await waitForJob(leadB2.task_id);
    setStepStatus(4, "done");
    setStepStatus(5, "active");

    const [aA, aB] = await Promise.all([lookupOne(USERNAME_A), lookupOne(USERNAME_B)]);
    // Before and After go into state together so they render together.
    setState({
      beforeA: bA,
      beforeB: bB,
      afterA: aA,
      afterB: aB,
      resultActorId: aA && aB && aA.id === aB.id ? aA.id : null,
    });
    setStepStatus(5, "done");
  } catch (err) {
    setState({
      error: err instanceof ApiError ? err.message : "Demo run failed",
      steps: state.steps.map((s) => (s.status === "active" ? { ...s, status: "error" as StepStatus } : s)),
    });
  } finally {
    setState({ running: false });
  }
}

export async function resetDemo() {
  if (state.running) return;
  setState({ running: true, error: null });
  try {
    const lead = await submitLead({
      username: USERNAME_B,
      platform: DEMO_PLATFORM,
      wallet: WALLET_B_BASELINE,
    });
    await waitForJob(lead.task_id);
    const [bA, bB] = await Promise.all([lookupOne(USERNAME_A), lookupOne(USERNAME_B)]);
    setState({
      afterA: null,
      afterB: null,
      resultActorId: null,
      beforeA: bA,
      beforeB: bB,
      steps: initialSteps(),
    });
  } catch (err) {
    setState({ error: err instanceof ApiError ? err.message : "Reset failed" });
  } finally {
    setState({ running: false });
  }
}
