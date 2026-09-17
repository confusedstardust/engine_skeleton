export type StoryGraph = {
  nodes: { id: string; label: string; kind: "start" | "scene" | "ending" | "missing" }[];
  edges: { id: string; source: string; target: string; label: string }[];
  warnings?: string[];
  revision?: number;
};

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
