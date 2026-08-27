import { useEffect, useMemo, useState } from "react";
import { ActorGraph, ApiError, getActorGraph } from "./api";
import { computeLayout } from "./forceLayout";

const WIDTH = 640;
const HEIGHT = 360;

const NODE_COLORS: Record<string, string> = {
  username: "#5b8cff",
  wallet: "#d9a441",
  pgp_key: "#4caf6d",
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

  const positions = useMemo(() => {
    if (!graph) return new Map<string, { x: number; y: number }>();
    const nodeIds = graph.nodes.map((n) => n.value);
    return computeLayout(nodeIds, graph.edges, WIDTH, HEIGHT);
  }, [graph]);

  if (error) {
    return <p className="error">{error}</p>;
  }

  if (!graph) {
    return <p className="muted">Loading relationship graph...</p>;
  }

  if (graph.nodes.length === 0) {
    return <p className="muted">No relationship data recorded for this actor yet.</p>;
  }

  return (
    <div className="graph-container">
      <svg width={WIDTH} height={HEIGHT} className="graph-svg">
        {graph.edges.map((edge, i) => {
          const source = positions.get(edge.source);
          const target = positions.get(edge.target);
          if (!source || !target) return null;
          const midX = (source.x + target.x) / 2;
          const midY = (source.y + target.y) / 2;
          return (
            <g key={i}>
              <line
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                className="graph-edge"
              />
              <text x={midX} y={midY} className="graph-edge-label">
                {edge.relationship}
              </text>
            </g>
          );
        })}
        {graph.nodes.map((node) => {
          const pos = positions.get(node.value);
          if (!pos) return null;
          const color = NODE_COLORS[node.type] ?? "#8a8f9c";
          return (
            <g key={node.value}>
              <circle cx={pos.x} cy={pos.y} r={10} fill={color} className="graph-node" />
              <text x={pos.x} y={pos.y + 24} className="graph-node-label">
                {node.value.length > 20 ? `${node.value.slice(0, 20)}...` : node.value}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="graph-legend">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <span key={type} className="graph-legend-item">
            <span className="graph-legend-swatch" style={{ background: color }} />
            {type}
          </span>
        ))}
      </div>
    </div>
  );
}
