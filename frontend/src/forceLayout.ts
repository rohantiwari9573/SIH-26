/** Minimal force-directed layout — no d3-force dependency, since these actor
 * graphs are small (a handful of nodes) and don't need a physics library.
 * Runs a fixed number of iterations synchronously and returns settled
 * positions; simple repulsion + spring attraction + centering, like a
 * stripped-down version of what d3-force does under the hood. */

export interface LayoutNode {
  id: string;
  x: number;
  y: number;
}

export interface LayoutEdge {
  source: string;
  target: string;
}

export function computeLayout(
  nodeIds: string[],
  edges: LayoutEdge[],
  width: number,
  height: number,
  iterations = 300
): Map<string, { x: number; y: number }> {
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) / 3;

  const positions = new Map<string, LayoutNode>();
  nodeIds.forEach((id, i) => {
    const angle = (2 * Math.PI * i) / Math.max(nodeIds.length, 1);
    positions.set(id, {
      id,
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    });
  });

  const REPULSION = 4000;
  const SPRING_LENGTH = 120;
  const SPRING_STRENGTH = 0.02;
  const CENTER_STRENGTH = 0.01;
  const DAMPING = 0.85;

  const velocities = new Map<string, { vx: number; vy: number }>();
  nodeIds.forEach((id) => velocities.set(id, { vx: 0, vy: 0 }));

  for (let iter = 0; iter < iterations; iter++) {
    const forces = new Map<string, { fx: number; fy: number }>();
    nodeIds.forEach((id) => forces.set(id, { fx: 0, fy: 0 }));

    for (let i = 0; i < nodeIds.length; i++) {
      for (let j = i + 1; j < nodeIds.length; j++) {
        const a = positions.get(nodeIds[i])!;
        const b = positions.get(nodeIds[j])!;
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const distSq = Math.max(dx * dx + dy * dy, 1);
        const dist = Math.sqrt(distSq);
        const force = REPULSION / distSq;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        forces.get(a.id)!.fx += fx;
        forces.get(a.id)!.fy += fy;
        forces.get(b.id)!.fx -= fx;
        forces.get(b.id)!.fy -= fy;
      }
    }

    for (const edge of edges) {
      const a = positions.get(edge.source);
      const b = positions.get(edge.target);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const displacement = dist - SPRING_LENGTH;
      const fx = (dx / dist) * displacement * SPRING_STRENGTH;
      const fy = (dy / dist) * displacement * SPRING_STRENGTH;
      forces.get(a.id)!.fx += fx;
      forces.get(a.id)!.fy += fy;
      forces.get(b.id)!.fx -= fx;
      forces.get(b.id)!.fy -= fy;
    }

    for (const id of nodeIds) {
      const pos = positions.get(id)!;
      forces.get(id)!.fx += (centerX - pos.x) * CENTER_STRENGTH;
      forces.get(id)!.fy += (centerY - pos.y) * CENTER_STRENGTH;
    }

    for (const id of nodeIds) {
      const vel = velocities.get(id)!;
      const force = forces.get(id)!;
      vel.vx = (vel.vx + force.fx) * DAMPING;
      vel.vy = (vel.vy + force.fy) * DAMPING;
      const pos = positions.get(id)!;
      pos.x += vel.vx;
      pos.y += vel.vy;
    }
  }

  const result = new Map<string, { x: number; y: number }>();
  positions.forEach((pos, id) => result.set(id, { x: pos.x, y: pos.y }));
  return result;
}
