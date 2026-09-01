import { useEffect, useMemo, useRef, useState } from "react";
import { ActorGraph, ActorProfile, ApiError, CorrelationEvidence, GraphEdge, getActorGraph } from "./api";
import { computeLayout } from "./forceLayout";
import { AlertIcon, KeyIcon, NetworkIcon, ServerIcon, UserIcon, WalletIcon } from "./icons";
import { SkeletonBlock } from "./Skeleton";

const WIDTH = 640;

const NODE_COLORS: Record<string, string> = {
  username: "var(--type-username)",
  wallet: "var(--type-wallet)",
  pgp_key: "var(--type-pgp_key)",
  onion_address: "var(--type-onion_address)",
};

const LEGEND_ITEMS: { type: string; label: string; icon: JSX.Element }[] = [
  { type: "username", label: "Handle", icon: <UserIcon width={11} height={11} /> },
  { type: "wallet", label: "Wallet", icon: <WalletIcon width={11} height={11} /> },
  { type: "pgp_key", label: "PGP key", icon: <KeyIcon width={11} height={11} /> },
  { type: "onion_address", label: "Infrastructure", icon: <ServerIcon width={11} height={11} /> },
  { type: "corr:*", label: "Threat/breach intel", icon: <NetworkIcon width={11} height={11} /> },
];

/** Relationship labels are shown on hover (native <title> tooltip) rather
 * than always-on floating text — with several edges converging on the same
 * two nodes (common once an actor has 2+ shared identifiers), always-on
 * labels overlapped each other no matter how the layout was tuned. A small
 * color-coded dot at the midpoint plus a tooltip scales to any edge density. */
const EDGE_COLORS: Record<string, string> = {
  USES_WALLET: "var(--type-wallet)",
  USES_KEY: "var(--type-pgp_key)",
  VOUCHES_FOR: "var(--accent)",
  RELATED_TO: "var(--type-onion_address)",
  MATCHES: "var(--low)",
};

const TYPE_LABELS: Record<string, string> = {
  username: "Handle",
  wallet: "Wallet address",
  pgp_key: "PGP key",
  onion_address: "Onion address (confirmed infra leak)",
};

// Correlation nodes (app.services.correlation) are typed "corr:<source>" —
// one dynamic prefix rather than a fixed set, so they're handled separately
// from the static TYPE_LABELS/NODE_COLORS maps above.
const CORR_PREFIX = "corr:";
const CORR_SOURCE_LABELS: Record<string, string> = {
  tor_onionoo: "Tor Onionoo match",
  misp_circl_osint: "MISP — CIRCL match",
  misp_botvrij_osint: "MISP — botvrij.eu match",
  hibp: "HIBP breach match",
};

function nodeColor(type: string): string {
  if (type.startsWith(CORR_PREFIX)) return "var(--low)";
  return NODE_COLORS[type] ?? "var(--low)";
}

function nodeTypeLabel(type: string): string {
  if (type.startsWith(CORR_PREFIX)) {
    const source = type.slice(CORR_PREFIX.length);
    return CORR_SOURCE_LABELS[source] ?? `External match (${source})`;
  }
  return TYPE_LABELS[type] ?? type;
}

// Matches app/api/routes/actors.py's ENTITY_TYPE_GROUPS / RELATIONSHIP_TYPE_GROUPS
// / SOURCE_FILTER_VALUES exactly — these are UI category keys the backend
// resolves into real Neo4j node types / relationship values / source_platform
// strings, not the raw values themselves. Filtering happens server-side in
// Cypher (see get_actor_relationship_graph), so counts below always reflect
// what was actually returned, never a client-side CSS-hidden subset.
const ENTITY_TYPE_OPTIONS: { key: string; label: string }[] = [
  { key: "handles", label: "Handles" },
  { key: "wallets", label: "Wallets" },
  { key: "pgp_keys", label: "PGP Keys" },
  { key: "infrastructure", label: "Infrastructure" },
  { key: "tor_intelligence", label: "Tor Intelligence" },
  { key: "threat_intelligence", label: "Threat Intelligence" },
  { key: "breach_intelligence", label: "Breach Intelligence" },
];

const RELATIONSHIP_TYPE_OPTIONS: { key: string; label: string }[] = [
  { key: "identity", label: "Identity" },
  { key: "financial", label: "Financial" },
  { key: "infrastructure", label: "Infrastructure" },
  { key: "threat_intelligence", label: "Threat Intelligence" },
];

const SOURCE_OPTIONS: { key: string; label: string }[] = [
  { key: "", label: "All Sources" },
  { key: "darkforums", label: "DarkForums" },
  { key: "evolution_market", label: "Evolution Market" },
  { key: "evolution_forum", label: "Evolution Forum" },
  { key: "tor_onionoo", label: "Tor Onionoo" },
  { key: "misp_circl", label: "MISP CIRCL" },
  { key: "misp_botvrij", label: "MISP botvrij.eu" },
  { key: "hibp", label: "HIBP" },
];

function CheckboxGroup({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: { key: string; label: string }[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  const [open, setOpen] = useState(false);
  const activeCount = selected.size;
  return (
    <div style={{ position: "relative" }}>
      <button
        className="btn-ghost"
        style={{ padding: "0.15rem 0.6rem", fontSize: "0.86rem" }}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
        {activeCount > 0 ? ` (${activeCount})` : ""} ▾
      </button>
      {open && (
        <div
          className="section-card"
          style={{
            position: "absolute",
            top: "1.8rem",
            left: 0,
            zIndex: 10,
            padding: "0.6rem",
            minWidth: 190,
            boxShadow: "var(--shadow-lg)",
          }}
        >
          {options.map((opt) => (
            <label
              key={opt.key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                fontSize: "0.86rem",
                padding: "0.2rem 0",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(opt.key)}
                onChange={() => {
                  const next = new Set(selected);
                  if (next.has(opt.key)) next.delete(opt.key);
                  else next.add(opt.key);
                  onChange(next);
                }}
              />
              {opt.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

type Selection = { kind: "node"; value: string } | { kind: "edge"; index: number } | null;

export default function GraphView({
  actorId,
  profile,
  evidence,
}: {
  actorId: string;
  profile?: ActorProfile | null;
  evidence?: CorrelationEvidence[] | null;
}) {
  const [graph, setGraph] = useState<ActorGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [depth, setDepth] = useState(1);
  const [entityTypes, setEntityTypes] = useState<Set<string>>(new Set());
  const [relationshipTypes, setRelationshipTypes] = useState<Set<string>>(new Set());
  const [source, setSource] = useState("");
  const [retryToken, setRetryToken] = useState(0);
  // Guards against out-of-order responses: rapidly changing depth/filters
  // fires overlapping requests, and a slower earlier response landing after
  // a faster later one would render a graph that doesn't match the
  // currently-selected filters, with no visible sign anything is wrong.
  const requestSeqRef = useRef(0);

  useEffect(() => {
    const seq = ++requestSeqRef.current;
    setGraph(null);
    setError(null);
    setSelection(null);
    getActorGraph(actorId, {
      depth,
      entityTypes: [...entityTypes],
      relationshipTypes: [...relationshipTypes],
      source: source || null,
    })
      .then((g) => {
        if (requestSeqRef.current === seq) setGraph(g);
      })
      .catch((err) => {
        if (requestSeqRef.current === seq) {
          setError(err instanceof ApiError ? err.message : "Failed to load relationship graph");
        }
      });
  }, [actorId, depth, entityTypes, relationshipTypes, source, retryToken]);

  function resetFilters() {
    setDepth(1);
    setEntityTypes(new Set());
    setRelationshipTypes(new Set());
    setSource("");
  }

  const filtersActive =
    depth !== 1 || entityTypes.size > 0 || relationshipTypes.size > 0 || source !== "";

  const selectedNode =
    selection?.kind === "node" ? graph?.nodes.find((n) => n.value === selection.value) ?? null : null;
  const selectedEdge = selection?.kind === "edge" ? graph?.edges[selection.index] ?? null : null;
  const nodeEdges =
    selection?.kind === "node"
      ? graph?.edges.filter((e) => e.source === selection.value || e.target === selection.value) ?? []
      : [];

  // Cross-references data the actor profile already fetched (profile.identifiers,
  // profile.infra_findings, the evidence list) rather than making another API
  // call — this is what lets the drawer answer "why does this edge exist" with
  // real provenance instead of a second round-trip.
  function identifierFor(value: string) {
    return profile?.identifiers.find((i) => i.value === value) ?? null;
  }
  function infraFindingFor(onionAddress: string) {
    return profile?.infra_findings.find((f) => f.onion_address === onionAddress) ?? null;
  }
  function evidenceForEdge(edge: GraphEdge): CorrelationEvidence | null {
    if (edge.relationship !== "MATCHES") return null;
    return (
      evidence?.find((e) => e.matched_value === edge.source || e.matched_value === edge.target) ??
      null
    );
  }

  // Scales with node count so a 2-3 node cluster isn't lost in a huge empty
  // canvas, while a busier graph still gets room to breathe.
  const height = useMemo(() => {
    if (!graph) return 220;
    return Math.min(420, Math.max(200, 90 + graph.nodes.length * 38));
  }, [graph]);

  const positions = useMemo(() => {
    if (!graph) return new Map<string, { x: number; y: number }>();
    const nodeIds = graph.nodes.map((n) => n.value);
    return computeLayout(nodeIds, graph.edges, WIDTH, height);
  }, [graph, height]);

  const toolbar = (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "0.5rem",
        padding: "0 1rem 0.75rem",
        fontSize: "0.86rem",
      }}
    >
      <span className="muted">Depth</span>
      {[1, 2, 3].map((d) => (
        <button
          key={d}
          className={depth === d ? "btn-secondary" : "btn-ghost"}
          style={{ padding: "0.15rem 0.6rem", fontSize: "0.86rem" }}
          onClick={() => setDepth(d)}
        >
          {d}
        </button>
      ))}
      <span style={{ width: 1, height: "1.1rem", background: "var(--border)" }} />
      <select
        value={source}
        onChange={(e) => setSource(e.target.value)}
        style={{ fontSize: "0.86rem", padding: "0.15rem 0.4rem" }}
      >
        {SOURCE_OPTIONS.map((opt) => (
          <option key={opt.key} value={opt.key}>
            {opt.label}
          </option>
        ))}
      </select>
      <CheckboxGroup
        label="Entity Types"
        options={ENTITY_TYPE_OPTIONS}
        selected={entityTypes}
        onChange={setEntityTypes}
      />
      <CheckboxGroup
        label="Relationships"
        options={RELATIONSHIP_TYPE_OPTIONS}
        selected={relationshipTypes}
        onChange={setRelationshipTypes}
      />
      {filtersActive && (
        <button className="btn-ghost" style={{ padding: "0.15rem 0.6rem", fontSize: "0.86rem" }} onClick={resetFilters}>
          Reset Filters
        </button>
      )}
      {graph && (
        <span className="muted" style={{ marginLeft: "auto", fontSize: "0.84rem" }}>
          Nodes: {graph.node_count} &nbsp;·&nbsp; Relationships: {graph.edge_count}
        </span>
      )}
    </div>
  );

  if (error) {
    return (
      <div>
        {toolbar}
        <div style={{ padding: "0 1.5rem 1.5rem" }}>
          <p className="error">
            <AlertIcon width={15} height={15} />
            {error}
          </p>
          <button onClick={() => setRetryToken((t) => t + 1)}>Retry</button>
        </div>
      </div>
    );
  }

  if (!graph) {
    return (
      <div>
        {toolbar}
        <div style={{ padding: "0 1.5rem 1.5rem" }}>
          <SkeletonBlock height={220} />
        </div>
      </div>
    );
  }

  if (graph.nodes.length === 0) {
    return (
      <div>
        {toolbar}
        <div style={{ padding: "0 1.5rem 1.5rem" }}>
          <p className="muted">
            {filtersActive
              ? "No entities in this actor's graph match the current filters."
              : "No relationship data recorded for this actor yet."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {toolbar}
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="graph-svg"
        style={{ padding: "0 1rem" }}
      >
        {/* Painted in three passes (not per-edge/per-node groups) so labels
            always sit above every line, and node labels above node fills —
            interleaving them let crossing edges cut through label text. */}
        {graph.edges.map((edge, i) => {
          const source = positions.get(edge.source);
          const target = positions.get(edge.target);
          if (!source || !target) return null;
          return (
            <line
              key={i}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              className="graph-edge"
            />
          );
        })}
        {graph.nodes.map((node) => {
          const pos = positions.get(node.value);
          if (!pos) return null;
          const color = nodeColor(node.type);
          const isSelected = selection?.kind === "node" && selection.value === node.value;
          return (
            <circle
              key={node.value}
              cx={pos.x}
              cy={pos.y}
              r={isSelected ? 14 : 11}
              fill={color}
              className="graph-node"
              style={{ cursor: "pointer" }}
              stroke={isSelected ? "var(--text-primary, #fff)" : "none"}
              strokeWidth={isSelected ? 2 : 0}
              onClick={() =>
                setSelection(isSelected ? null : { kind: "node", value: node.value })
              }
            >
              <title>{`${nodeTypeLabel(node.type)}: ${node.value}`}</title>
            </circle>
          );
        })}
        {graph.edges.map((edge, i) => {
          const source = positions.get(edge.source);
          const target = positions.get(edge.target);
          if (!source || !target) return null;
          const midX = (source.x + target.x) / 2;
          const midY = (source.y + target.y) / 2;
          const isSelected = selection?.kind === "edge" && selection.index === i;
          return (
            <circle
              key={i}
              cx={midX}
              cy={midY}
              r={isSelected ? 6 : 4}
              fill={EDGE_COLORS[edge.relationship] ?? "var(--text-muted)"}
              stroke="var(--surface-1)"
              strokeWidth={isSelected ? 2.5 : 1.5}
              style={{ cursor: "pointer" }}
              onClick={() => setSelection(isSelected ? null : { kind: "edge", index: i })}
            >
              <title>{edge.relationship}</title>
            </circle>
          );
        })}
        {graph.nodes.map((node) => {
          const pos = positions.get(node.value);
          if (!pos) return null;
          const label =
            node.value.length > 20 ? `${node.value.slice(0, 20)}...` : node.value;
          return (
            <g key={node.value}>
              <rect
                x={pos.x - label.length * 3}
                y={pos.y + 17}
                width={label.length * 6}
                height={13}
                rx={3}
                fill="var(--surface-1)"
              />
              <text x={pos.x} y={pos.y + 26} className="graph-node-label">
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="graph-legend">
        {LEGEND_ITEMS.map(({ type, label, icon }) => (
          <span key={type} className="graph-legend-item">
            <span className="graph-legend-swatch" style={{ background: nodeColor(type) }} />
            {icon}
            {label}
          </span>
        ))}
        <span style={{ width: 1, height: "0.9rem", background: "var(--border)" }} />
        {Object.entries(EDGE_COLORS).map(([relationship, color]) => (
          <span key={relationship} className="graph-legend-item">
            <span className="graph-legend-swatch" style={{ background: color }} />
            {relationship.toLowerCase().replace(/_/g, " ")}
          </span>
        ))}
      </div>

      {/* Evidence drawer — always rendered so the investigator sees the
          "select something" prompt rather than the panel appearing/disappearing.
          Distinct surface (surface-2, not the outer card's surface-1) so it
          reads as its own panel rather than blending into the graph card. */}
      <div
        className="section-card"
        style={{ margin: "1.1rem 1rem 1rem", background: "var(--surface-2)" }}
      >
        <div className="section-heading">
          <h3 style={{ fontSize: "1rem" }}>Evidence</h3>
        </div>
        {!selectedNode && !selectedEdge && (
          <p className="muted">Select a node or relationship to inspect evidence.</p>
        )}

        {selectedNode && (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
              <span
                className="graph-legend-swatch"
                style={{ background: nodeColor(selectedNode.type) }}
              />
              <strong style={{ fontSize: "0.85rem" }}>{nodeTypeLabel(selectedNode.type)}</strong>
            </div>
            <p className="mono" style={{ marginBottom: "0.6rem", wordBreak: "break-all" }}>
              {selectedNode.value}
            </p>
            <dl className="evidence-fields">
              <dt>Associated entities</dt>
              <dd>{nodeEdges.length}</dd>
              <dt>Source</dt>
              <dd>{selectedNode.source_platform ?? "—"}</dd>
              {identifierFor(selectedNode.value) && (
                <>
                  <dt>First observed</dt>
                  <dd>{new Date(identifierFor(selectedNode.value)!.first_seen).toLocaleString()}</dd>
                  <dt>Last observed</dt>
                  <dd>{new Date(identifierFor(selectedNode.value)!.last_seen).toLocaleString()}</dd>
                </>
              )}
              {selectedNode.type === "onion_address" && infraFindingFor(selectedNode.value) && (
                <>
                  <dt>Discovered</dt>
                  <dd>{new Date(infraFindingFor(selectedNode.value)!.discovered_at).toLocaleString()}</dd>
                </>
              )}
            </dl>
            {nodeEdges.length > 0 && (
              <>
                <p className="muted" style={{ fontSize: "0.85rem", margin: "0.6rem 0 0.3rem" }}>
                  Relationships:
                </p>
                <ul style={{ fontSize: "0.85rem", paddingLeft: "1.1rem" }}>
                  {nodeEdges.map((e, i) => {
                    const other = e.source === selectedNode.value ? e.target : e.source;
                    return (
                      <li key={i}>
                        <span className="mono">{other}</span>{" "}
                        <span className="muted">
                          ({e.relationship.toLowerCase().replace(/_/g, " ")}, weight{" "}
                          {(e.weight * 100).toFixed(0)}%)
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
          </div>
        )}

        {selectedEdge && (
          <div>
            <div className="persona-link-pair" style={{ marginBottom: "0.6rem" }}>
              <span className="mono">{selectedEdge.source}</span>
              <span className="muted">→ {selectedEdge.relationship.replace(/_/g, " ")} →</span>
              <span className="mono">{selectedEdge.target}</span>
            </div>
            <p className="muted" style={{ fontSize: "0.86rem", marginBottom: "0.5rem" }}>
              WHY THIS RELATIONSHIP EXISTS
            </p>
            {(() => {
              const ev = evidenceForEdge(selectedEdge);
              if (ev) {
                return (
                  <dl className="evidence-fields">
                    <dt>Evidence type</dt>
                    <dd>Deterministic indicator match</dd>
                    <dt>Source</dt>
                    <dd>{CORR_SOURCE_LABELS[ev.source]?.replace(" match", "") ?? ev.source}</dd>
                    <dt>Source record</dt>
                    <dd className="mono">{ev.source_record_id}</dd>
                    <dt>Matched value</dt>
                    <dd className="mono">{ev.matched_value}</dd>
                    <dt>Observed</dt>
                    <dd>{ev.observed_at ? new Date(ev.observed_at).toLocaleDateString() : "—"}</dd>
                    <dt>Ingested</dt>
                    <dd>{new Date(ev.ingested_at).toLocaleString()}</dd>
                    <dt>Description</dt>
                    <dd>{ev.description}</dd>
                  </dl>
                );
              }
              // Identity/financial/infra edges (USES_WALLET, USES_KEY,
              // VOUCHES_FOR, RELATED_TO) aren't backed by a CorrelationEvidence
              // row — their real provenance is simply which platform the
              // identifier was actually observed on, from profile.identifiers.
              const targetIdent = identifierFor(selectedEdge.target) ?? identifierFor(selectedEdge.source);
              return (
                <dl className="evidence-fields">
                  <dt>Evidence</dt>
                  <dd>Direct identifier match</dd>
                  <dt>Source</dt>
                  <dd>{targetIdent?.source_platform ?? "—"}</dd>
                  <dt>Weight</dt>
                  <dd>{(selectedEdge.weight * 100).toFixed(0)}%</dd>
                </dl>
              );
            })()}
          </div>
        )}
      </div>
    </div>
  );
}
