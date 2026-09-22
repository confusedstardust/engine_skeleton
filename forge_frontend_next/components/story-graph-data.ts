export type StoryGraph = {
  nodes: {
    id: string;
    label: string;
    kind: "start" | "scene" | "ending" | "missing";
    internalContinuationCount?: number;
    internalLoopCount?: number;
    internalLoopLabels?: string[];
  }[];
  edges: { id: string; source: string; target: string; label: string }[];
  warnings?: string[];
  revision?: number;
};

export function readingNodeIds(graph: StoryGraph, count = 3): string[] {
  return graph.nodes.slice(0, Math.max(1, count)).map(node => node.id);
}

export function relatedNodeIds(graph: StoryGraph, nodeId: string): string[] {
  const ids = new Set([nodeId]);
  graph.edges.forEach(edge => {
    if (edge.source === nodeId) ids.add(edge.target);
    if (edge.target === nodeId) ids.add(edge.source);
  });
  return [...ids];
}

/**
 * Finds DFS back-edges: the particular arrows that return to a scene already
 * on the active story path. Excluding these arrows from layout keeps the main
 * reading direction stable while still rendering the loop itself.
 */
export function returnEdgeIds(graph: StoryGraph): Set<string> {
  const outgoing = new Map<string, StoryGraph["edges"]>();
  graph.edges.forEach(edge => outgoing.set(edge.source, [...(outgoing.get(edge.source) || []), edge]));
  const state = new Map<string, "visiting" | "visited">();
  const returns = new Set<string>();
  const visit = (nodeId: string) => {
    state.set(nodeId, "visiting");
    for (const edge of outgoing.get(nodeId) || []) {
      const targetState = state.get(edge.target);
      if (targetState === "visiting") returns.add(edge.id);
      else if (!targetState) visit(edge.target);
    }
    state.set(nodeId, "visited");
  };
  graph.nodes.forEach(node => { if (!state.has(node.id)) visit(node.id); });
  return returns;
}

export function primaryRouteEdgeIds(graph: StoryGraph, ignoredEdgeIds = new Set<string>()): Set<string> {
  const outgoing = new Map<string, StoryGraph["edges"]>();
  const incoming = new Map<string, number>();
  graph.edges.forEach(edge => {
    if (ignoredEdgeIds.has(edge.id)) return;
    outgoing.set(edge.source, [...(outgoing.get(edge.source) || []), edge]);
    incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1);
  });
  const starts = [
    ...graph.nodes.filter(node => node.kind === "start"),
    ...graph.nodes.filter(node => node.kind !== "start" && !incoming.has(node.id)),
    ...graph.nodes
  ];
  const discovered = new Set<string>();
  const primary = new Set<string>();
  for (const start of starts) {
    if (discovered.has(start.id)) continue;
    discovered.add(start.id);
    const queue = [start.id];
    while (queue.length) {
      const id = queue.shift()!;
      for (const edge of outgoing.get(id) || []) {
        if (discovered.has(edge.target)) continue;
        discovered.add(edge.target);
        primary.add(edge.id);
        queue.push(edge.target);
      }
    }
  }
  return primary;
}

export function compactStoryPositions(graph: StoryGraph, ignoredEdgeIds = new Set<string>()) {
  const outgoing = new Map<string, StoryGraph["edges"]>();
  const incoming = new Map<string, number>();
  graph.edges.forEach(edge => {
    if (ignoredEdgeIds.has(edge.id)) return;
    outgoing.set(edge.source, [...(outgoing.get(edge.source) || []), edge]);
    incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1);
  });
  const starts = [
    ...graph.nodes.filter(node => node.kind === "start"),
    ...graph.nodes.filter(node => node.kind !== "start" && !incoming.has(node.id)),
    ...graph.nodes
  ];
  const seen = new Set<string>();
  const order: string[] = [];
  for (const start of starts) {
    if (seen.has(start.id)) continue;
    const queue = [start.id];
    while (queue.length) {
      const id = queue.shift()!;
      if (seen.has(id)) continue;
      seen.add(id);
      order.push(id);
      for (const edge of outgoing.get(id) || []) queue.push(edge.target);
    }
  }
  const columns = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(order.length * 1.25))));
  const positions = new Map<string, { x: number; y: number; order: number }>();
  order.forEach((id, index) => {
    const row = Math.floor(index / columns);
    const slot = index % columns;
    const column = row % 2 === 0 ? slot : columns - 1 - slot;
    positions.set(id, { x: column * 320, y: row * 220, order: index + 1 });
  });
  return positions;
}

export function nearestCardHandles(
  source: { x: number; y: number },
  target: { x: number; y: number },
  cardWidth = 220,
  cardHeight = 124
) {
  const dx = (target.x - source.x) / cardWidth;
  const dy = (target.y - source.y) / cardHeight;
  if (dx === 0 && dy === 0) return { sourceHandle: "source-top", targetHandle: "target-right" };
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0
    ? { sourceHandle: "source-right", targetHandle: "target-left" }
    : { sourceHandle: "source-left", targetHandle: "target-right" };
  return dy >= 0
    ? { sourceHandle: "source-bottom", targetHandle: "target-top" }
    : { sourceHandle: "source-top", targetHandle: "target-bottom" };
}

type Plan = {
  story_progression: { id: string; name: string }[];
  endings: { ending_type: string; id?: string; name?: string }[];
  narrative_structure?: string;
};

export function planningGraph(plan: Plan): StoryGraph {
  const nodes: StoryGraph["nodes"] = plan.story_progression.map((step, index) => ({
    id: step.id || `phase${index}`, label: step.name || step.id, kind: index === 0 ? "start" : "scene"
  }));
  const aliases = new Map(nodes.map(node => [node.id, node.id]));
  plan.endings.forEach((ending, index) => {
    const id = ending.id || `ending_${index + 1}`;
    if (!nodes.some(node => node.id === id)) nodes.push({ id, label: ending.name || `结局：${ending.ending_type}`, kind: "ending" });
    for (const alias of [id, ending.ending_type.replace(/[^A-Za-z0-9_]/g, "_"), `ending_${index + 1}`]) aliases.set(alias, id);
    for (const name of ["true", "normal", "branch", "hidden"]) {
      if (ending.ending_type.toLowerCase().includes(name)) {
        for (const alias of [`${name}_ending`, `ending_${name}`]) if (!aliases.has(alias)) aliases.set(alias, id);
      }
    }
  });
  const source = plan.narrative_structure || "";
  const declarations = /\b([A-Za-z_][\w-]*)\s*(?:\[([^\]]+)\]|\(([^)]+)\)|\{([^}]+)\})/g;
  const labels = new Map<string, string>();
  for (const match of source.matchAll(declarations)) labels.set(match[1], (match[2] || match[3] || match[4]).replace(/^"|"$/g, ""));
  const ensure = (raw: string) => {
    const id = aliases.get(raw) || raw;
    if (!nodes.some(node => node.id === id)) nodes.push({ id, label: labels.get(raw) || raw, kind: "scene" });
    return id;
  };
  const edges: StoryGraph["edges"] = [];
  const pattern = /\b(?=([A-Za-z_][\w-]*)(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\})?\s*(?:-->|==>|-\.->)\s*(?:\|([^|]+)\|\s*)?([A-Za-z_][\w-]*))/g;
  for (const line of source.split(/\r?\n/).filter(line => !line.trim().startsWith("%%"))) {
    for (const match of line.matchAll(pattern)) {
      const source = ensure(match[1]), target = ensure(match[3]), label = match[2] || "";
      if (!edges.some(edge => edge.source === source && edge.target === target && edge.label === label)) edges.push({ id: `plan-${edges.length}`, source, target, label });
    }
  }
  return { nodes, edges, warnings: source.trim() && !edges.length ? ["暂未识别到流程连线，请同步流程图后再查看。"] : [] };
}
