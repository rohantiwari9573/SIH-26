import { useEffect, useMemo, useState } from "react";
import { ActorGraph, ApiError, getActorGraph } from "./api";
import { computeLayout } from "./forceLayout";
import { AlertIcon, KeyIcon, UserIcon, WalletIcon } from "./icons";

const WIDTH = 640;

const NODE_COLORS: Record<string, string> = {
  username: "var(--type-username)",
  wallet: "var(--type-wallet)",
  pgp_key: "var(--type-pgp_key)",
};

const LEGEND_ITEMS: { type: string; label: string; icon: JSX.Element }[] = [
  { type: "username", label: "username", icon: <UserIcon width={11} height={11} /> },
  { type: "wallet", label: "wallet", icon: <WalletIcon width={11} height={11} /> },
  { type: "pgp_key", label: "PGP key", icon: <KeyIcon width={11} height={11} /> },
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
};

export default function GraphView({ actorId }: { actorId: string }) {
  const [graph, setGraph] = useState<ActorGraph | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setGraph(null);
    setError(null);
    getActorGraph(actorId)
      .then(setGraph)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load relationship graph")
      );
  }, [actorId]);

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

  if (error) {
    return (
      <div style={{ padding: "0 1.5rem 1.5rem" }}>
        <p className="error">
          <AlertIcon width={15} height={15} />
          {error}
        </p>
      </div>
    );
  }

  if (!graph) {
    return (
      <div style={{ padding: "0 1.5rem 1.5rem" }}>
        <p className="muted">Loading relationship graph...</p>
      </div>
    );
  }

  if (graph.nodes.length === 0) {
    return (
      <div style={{ padding: "0 1.5rem 1.5rem" }}>
        <p className="muted">No relationship data recorded for this actor yet.</p>
      </div>
    );
  }

  return (
    <div>
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
          const color = NODE_COLORS[node.type] ?? "var(--low)";
          return (
            <circle
              key={node.value}
              cx={pos.x}
              cy={pos.y}
              r={11}
              fill={color}
              className="graph-node"
            />
          );
        })}
        {graph.edges.map((edge, i) => {
          const source = positions.get(edge.source);
          const target = positions.get(edge.target);
          if (!source || !target) return null;
          const midX = (source.x + target.x) / 2;
          const midY = (source.y + target.y) / 2;
          return (
            <circle
              key={i}
              cx={midX}
              cy={midY}
              r={4}
              fill={EDGE_COLORS[edge.relationship] ?? "var(--text-muted)"}
              stroke="var(--surface-1)"
              strokeWidth={1.5}
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
            <span className="graph-legend-swatch" style={{ background: NODE_COLORS[type] }} />
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
    </div>
  );
}
