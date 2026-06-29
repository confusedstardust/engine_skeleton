export type Job = {
  id: string;
  status: string;
  phase?: string | null;
  error?: string | null;
  options?: {
    generation_mode?: string;
    [key: string]: unknown;
  };
};

export type NodeArtifact = {
  key: string;
  phase: string;
  phase_status: string;
  title: string;
  description: string;
  path: string;
  content_type: "json" | "text";
  exists: boolean;
  content: string | null;
};

export type NodesResponse = {
  job: Job;
  nodes: NodeArtifact[];
  scenes: NodeArtifact[];
};

export type AssetReviewItem = {
  filename: string;
  subdir: string;
  kind: string;
  display_name?: string;
  size: string;
  prompt: string;
  available_scene: string;
  scene_display_name?: string;
  exists: boolean;
  url: string;
  avatar_exists: boolean;
  avatar_url: string | null;
};

export type AssetReviewResponse = {
  job: Job;
  assets: AssetReviewItem[];
  image_enabled: boolean;
};

export type StoryStep = {
  id: string;
  name: string;
  content: string;
  narrative_target: string;
  strtype: string;
};

export type NarrativeCharacter = {
  id: string;
  name: string;
  gender: string;
  personality: string;
  motivation: string;
  speech_style: string;
  emotional_arc: string;
  relationships: { with: string; dynamic: string }[];
};

export type NarrativeEnding = {
  ending_type: string;
  description: string;
};

export type NarrativeNodeKind = "phase" | "ending" | "character";

export type GeneratedNarrativeNodeResponse = {
  kind: NarrativeNodeKind;
  node: StoryStep | NarrativeEnding | NarrativeCharacter;
};

export type SyncNarrativeStructureResponse = {
  narrative_plan: NarrativePlan;
  narrative_structure: string;
  issues: { node: string; reason: string }[];
};

export type SyncNarrativeStructureOptions = {
  quiet?: boolean;
  force?: boolean;
};

export type NarrativePlan = {
  title: string;
  theme: string;
  emotion_tone: string;
  conflict_structure: string;
  story_progression: StoryStep[];
  story_arc: string;
  characters: NarrativeCharacter[];
  touchable_points: string[];
  must_avoid: string[];
  endings: NarrativeEnding[];
  beat_structure: string[];
  narrative_structure: string;
};

export type ScenePlan = {
  scenes: {
    kind?: "Scene";
    scene_file: string;
    source_node: string;
    node_name: string;
    strtype: string;
  }[];
  endings: {
    kind?: "Ending";
    scene_file: string;
    ending_type: string;
    description: string;
  }[];
};

export type SceneDraft = {
  header: string;
  title: string;
  lines: SceneLine[];
  marker?: "Scene" | "Ending";
  sourceNode?: string;
  strtype?: string;
};

export type GameDesignDraftScene = SceneDraft & {
  marker: "Scene" | "Ending";
  sourceNode: string;
  endingType: string;
};

export type SceneLine = {
  id: string;
  kind: "narration" | "dialogue" | "command" | "choice" | "branch";
  speaker: string;
  text: string;
  rawPrefix: string;
  choices?: SceneChoice[];
  branchLabel?: string;
};

export type SceneChoice = {
  text: string;
  target: string;
  target_scene_file?: string;
  targetSceneFile?: string;
};

type GameDesignJsonScene = Partial<GameDesignDraftScene> & {
  scene_file?: string;
  source_node?: string;
  ending_type?: string;
};

type SceneMeta = {
  title: string;
  marker: "Scene" | "Ending";
  sourceNode: string;
  strtype: string;
};

export function compactId(id: string) {
  return `${id.slice(0, 8)}...${id.slice(-4)}`;
}

export function parsePlan(content: string | null): NarrativePlan | null {
  if (!content) return null;
  try {
    const parsed = JSON.parse(content) as Partial<NarrativePlan>;
    return {
      title: parsed.title || "",
      theme: parsed.theme || "",
      emotion_tone: parsed.emotion_tone || "",
      conflict_structure: parsed.conflict_structure || "",
      story_progression: parsed.story_progression || [],
      story_arc: parsed.story_arc || "",
      characters: parsed.characters || [],
      touchable_points: parsed.touchable_points || [],
      must_avoid: parsed.must_avoid || [],
      endings: parsed.endings || [],
      beat_structure: parsed.beat_structure || [],
      narrative_structure: parsed.narrative_structure || ""
    };
  } catch {
    return null;
  }
}

function flowNodeId(value: string) {
  const normalized = value.trim().replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  if (!normalized) return "";
  return /^[A-Za-z_]/.test(normalized) ? normalized : `node_${normalized}`;
}

function flowNodeLabel(id: string, plan: NarrativePlan) {
  const phase = plan.story_progression.find((step) => flowNodeId(step.id) === id || step.id === id || step.name === id);
  if (phase) return phase.name || phase.id;
  const ending = plan.endings.find((item) => flowNodeId(item.ending_type) === id || item.ending_type === id);
  if (ending) return `结局：${ending.ending_type}`;
  return id.replace(/_/g, " ");
}

export function parseFlowEdges(structure: string, plan: NarrativePlan) {
  const edgePattern = /([A-Za-z_][A-Za-z0-9_-]*)(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})?\s*(?:-->|==>|-\.->)\s*(?:\|[^|]+\|\s*)?([A-Za-z_][A-Za-z0-9_-]*)/g;
  const edges: { source: string; target: string }[] = [];
  for (const line of structure.split(/\r?\n/)) {
    edgePattern.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = edgePattern.exec(line))) {
      edges.push({ source: flowNodeLabel(match[1], plan), target: flowNodeLabel(match[2], plan) });
    }
  }
  return edges;
}

export function flowNodes(plan: NarrativePlan) {
  return [
    ...plan.story_progression.map((step, index) => ({
      id: flowNodeId(step.id || `phase${index}`),
      label: step.name || step.id || `阶段 ${index + 1}`,
      meta: step.strtype === "branch" ? "分支" : "主线"
    })),
    ...plan.endings.map((ending, index) => ({
      id: flowNodeId(ending.ending_type || `ending_${index + 1}`),
      label: `结局：${ending.ending_type || index + 1}`,
      meta: "结局"
    }))
  ];
}

export function parseScenePlan(content: string | null): ScenePlan | null {
  if (!content) return null;
  try {
    const parsed = JSON.parse(content) as Partial<ScenePlan>;
    return {
      scenes: parsed.scenes || [],
      endings: parsed.endings || []
    };
  } catch {
    return null;
  }
}

function scenePlanMetaByHeader(scenePlan: ScenePlan | null, plan: NarrativePlan | null) {
  const mapping = new Map<string, SceneMeta>();
  if (!scenePlan) return mapping;
  scenePlan.scenes.forEach((scene, index) => {
    const sourceNode = String(scene.source_node || "").trim();
    const phase = plan?.story_progression.find((step) => step.id === sourceNode || step.name === sourceNode);
    const title = String(scene.node_name || phase?.name || `场景 ${index + 1}`).trim();
    mapping.set(scene.scene_file, {
      title,
      marker: "Scene",
      sourceNode,
      strtype: normalizeStrtype(scene.strtype || phase?.strtype)
    });
  });
  scenePlan.endings.forEach((ending, index) => {
    const endingType = String(ending.ending_type || "").trim();
    mapping.set(ending.scene_file, {
      title: endingType ? `结局：${endingType}` : `结局 ${index + 1}`,
      marker: "Ending",
      sourceNode: "",
      strtype: ""
    });
  });
  return mapping;
}

function isBranchLabel(value: string | undefined) {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test((value || "").trim());
}

function normalizeSceneChoice(choice: Partial<SceneChoice> | string, fallbackIndex: number): SceneChoice {
  if (typeof choice === "string") {
    return { text: choice, target: `choice_${fallbackIndex}` };
  }
  const targetSceneFile = choice.target_scene_file || choice.targetSceneFile || "";
  return {
    text: choice.text || "",
    target: choice.target || targetSceneFile || `choice_${fallbackIndex}`,
    target_scene_file: targetSceneFile || undefined
  };
}

function normalizeSceneLine(line: Partial<SceneLine>, fallbackId: string): SceneLine {
  const branchLabel = line.branchLabel || line.text || "";
  const kind = line.kind === "branch" && !isBranchLabel(branchLabel) ? "narration" : line.kind || "narration";
  return {
    id: line.id || fallbackId,
    kind,
    speaker: line.speaker || (kind === "dialogue" ? "角色" : kind === "choice" || kind === "branch" ? "分支" : "旁白"),
    text: line.text || "",
    rawPrefix: line.rawPrefix || (kind === "choice" ? "choose" : kind === "branch" ? "branch" : "旁白"),
    choices: Array.isArray(line.choices) ? line.choices.map((choice, index) => normalizeSceneChoice(choice, index + 1)) : undefined,
    branchLabel: kind === "branch" ? line.branchLabel : undefined
  };
}

function scenesFromGameDesignJson(content: string, plan: NarrativePlan | null, scenePlan: ScenePlan | null): GameDesignDraftScene[] | null {
  try {
    const parsed = JSON.parse(content) as { scenes?: GameDesignJsonScene[] };
    if (!Array.isArray(parsed.scenes)) return null;
    const metaByHeader = scenePlanMetaByHeader(scenePlan, plan);
    return parsed.scenes.map((scene, index) => {
      const header = String(scene.scene_file || scene.header || `scene_${index}.txt`);
      const meta = metaByHeader.get(header);
      const marker = scene.marker || meta?.marker || "Scene";
      const sourceNode = String(scene.sourceNode || scene.source_node || meta?.sourceNode || "");
      const endingType = String(scene.endingType || scene.ending_type || "");
      const lines = Array.isArray(scene.lines) ? scene.lines.map((line, lineIndex) => normalizeSceneLine(line, `${header}-${lineIndex}`)) : [];
      return {
        header,
        marker,
        sourceNode,
        endingType,
        title: String(scene.title || meta?.title || draftSceneTitle({ header, marker, sourceNode, endingType, title: "", lines }, index, plan)),
        strtype: String(scene.strtype || meta?.strtype || storyStepStrtype(plan, sourceNode)),
        lines
      };
    });
  } catch {
    return null;
  }
}

function scenesFromCompletedJson(content: string, plan: NarrativePlan | null, scenePlan: ScenePlan | null): SceneDraft[] | null {
  const draftScenes = scenesFromGameDesignJson(content, plan, scenePlan);
  if (!draftScenes) return null;
  return draftScenes.map((scene) => ({ ...scene }));
}

export function serializeGameDesignJson(scenes: SceneDraft[]) {
  return JSON.stringify(
    {
      version: 1,
      scenes: scenes.map((scene) => ({
        marker: scene.marker || "Scene",
        scene_file: scene.header,
        source_node: scene.sourceNode || "",
        ending_type: "endingType" in scene ? (scene as GameDesignDraftScene).endingType || "" : "",
        title: scene.title,
        strtype: scene.strtype || "",
        lines: scene.lines
      }))
    },
    null,
    2
  );
}

export function parseGameDesignDraft(text: string, plan: NarrativePlan | null, scenePlan: ScenePlan | null = null): GameDesignDraftScene[] {
  const fromJson = scenesFromGameDesignJson(text, plan, scenePlan);
  if (fromJson) return fromJson;
  const scenes: GameDesignDraftScene[] = [];
  let current: GameDesignDraftScene | null = null;
  const metaByHeader = scenePlanMetaByHeader(scenePlan, plan);

  text.split(/\r?\n/).forEach((line, index) => {
    const trimmed = line.trim();
    const sceneMatch = trimmed.match(/^(Scene|Ending)\s*[:：]\s*(.+)$/i);
    if (sceneMatch) {
      const header = sceneMatch[2].trim();
      const meta = metaByHeader.get(header);
      current = {
        marker: meta?.marker || (sceneMatch[1].toLowerCase() === "ending" ? "Ending" : "Scene"),
        header,
        sourceNode: meta?.sourceNode || "",
        endingType: "",
        title: meta?.title || "",
        lines: [],
        strtype: meta?.strtype
      };
      scenes.push(current);
      return;
    }

    const sourceMatch = trimmed.match(/^;?\s*source_node\s*[:：]\s*(.+)$/i);
    if (sourceMatch && current) {
      current.sourceNode = sourceMatch[1].trim();
      current.title = draftSceneTitle(current, scenes.length - 1, plan);
      current.strtype = current.strtype || storyStepStrtype(plan, current.sourceNode);
      return;
    }

    const endingTypeMatch = trimmed.match(/^;?\s*ending_type\s*[:：]\s*(.+)$/i);
    if (endingTypeMatch && current) {
      current.endingType = endingTypeMatch[1].trim();
      current.title = draftSceneTitle(current, scenes.length - 1, plan);
      return;
    }

    if (!trimmed) return;
    if (!current) {
      current = {
        marker: "Scene",
        header: "draft.txt",
        sourceNode: "",
        endingType: "",
        title: "场景草稿",
        lines: []
      };
      scenes.push(current);
    }
    current.lines.push(parseGameDesignDraftLine(line, `${current.header}-${index}`));
  });

  return scenes.map((scene, index) => ({
    ...scene,
    title: scene.title || draftSceneTitle(scene, index, plan)
  }));
}

function draftSceneTitle(scene: GameDesignDraftScene, index: number, plan: NarrativePlan | null) {
  const source = scene.sourceNode || scene.endingType || scene.header.replace(/\.txt$/i, "");
  const phase = plan?.story_progression.find((step) => step.id === source);
  if (phase) return phase.name || `故事阶段 ${index + 1}`;
  const ending = plan?.endings.find((item) => item.ending_type === source || source.includes(item.ending_type));
  if (ending) return `结局：${ending.ending_type}`;
  if (/^start/i.test(scene.header)) return "开场";
  if (scene.marker === "Ending" || /^ending/i.test(scene.header)) return `结局 ${index + 1}`;
  return `场景 ${index + 1}`;
}

export function normalizeStrtype(strtype?: string) {
  const normalized = (strtype || "").trim().toLowerCase();
  if (normalized === "branch") return "branch";
  if (normalized === "main") return "main";
  return "";
}

function strtypeLabel(strtype?: string) {
  const normalized = normalizeStrtype(strtype);
  if (normalized === "branch") return "分支";
  if (normalized === "main") return "主线";
  return "";
}

function storyStepStrtype(plan: NarrativePlan | null, sourceNode?: string) {
  if (!plan || !sourceNode) return "";
  return normalizeStrtype(plan.story_progression.find((step) => step.id === sourceNode || step.name === sourceNode)?.strtype);
}

export function draftSceneRouteLabel(scene: GameDesignDraftScene, plan: NarrativePlan | null) {
  const label = strtypeLabel(storyStepStrtype(plan, scene.sourceNode || scene.header.replace(/\.txt$/i, "")));
  if (label) return label;
  return scene.marker === "Ending" ? "结局" : "未标注";
}

export function completedSceneRouteLabel(scene: SceneDraft) {
  return strtypeLabel(scene.strtype) || "未标注";
}

export function sceneMarkerLabel(scene: Pick<SceneDraft, "marker">) {
  return scene.marker === "Ending" ? "结局" : "场景";
}

export function choiceTargetValue(choice: SceneChoice) {
  return choice.target_scene_file || choice.targetSceneFile || choice.target || "";
}

export function sceneTargetOptions(scenePlan: ScenePlan | null, plan: NarrativePlan | null, scenes: SceneDraft[], currentHeader?: string) {
  const byHeader = scenePlanMetaByHeader(scenePlan, plan);
  scenes.forEach((scene) => {
    if (!byHeader.has(scene.header)) {
      byHeader.set(scene.header, {
        title: scene.title || scene.header.replace(/\.txt$/i, "").replace(/_/g, " "),
        marker: scene.marker || "Scene",
        sourceNode: scene.sourceNode || "",
        strtype: scene.strtype || ""
      });
    }
  });
  return Array.from(byHeader.entries())
    .filter(([file]) => file !== currentHeader)
    .map(([file, meta]) => ({
      file,
      label: meta.marker === "Ending" ? `结局：${meta.title.replace(/^结局[:：]/, "")}` : meta.title || file
    }));
}

function parseGameDesignDraftLine(line: string, id: string): SceneLine {
  const trimmed = line.trim().replace(/^>\s*/, "");
  const narrationMatch = trimmed.match(/^(旁白|intro)\s*[:：]\s*(.*?);?$/);
  if (narrationMatch) {
    return { id, kind: "narration", speaker: "旁白", text: cleanEditableLineText(narrationMatch[2]), rawPrefix: narrationMatch[1] === "intro" ? "intro" : "旁白" };
  }

  const dialogueMatch = trimmed.match(/^([^:：;]{1,24})[:：]\s*(.*?);?$/);
  if (dialogueMatch && !trimmed.startsWith("setVar") && !trimmed.startsWith("change") && !trimmed.startsWith("choose")) {
    return { id, kind: "dialogue", speaker: dialogueMatch[1].trim(), text: cleanEditableLineText(dialogueMatch[2]), rawPrefix: "" };
  }

  return { id, kind: "narration", speaker: "旁白", text: cleanEditableLineText(trimmed), rawPrefix: "intro" };
}

function cleanEditableLineText(text: string) {
  return text.replace(/^\s*[:：]\s*/, "").replace(/\s*;\s*$/, "");
}

function parseChoiceOptions(text: string): SceneChoice[] {
  return text
    .replace(/\s*;\s*$/, "")
    .split("|")
    .map((part) => {
      const trimmed = part.trim();
      const targetSplit = trimmed.lastIndexOf(":");
      if (targetSplit <= 0) return null;
      const choiceText = trimmed.slice(0, targetSplit).trim();
      const target = trimmed.slice(targetSplit + 1).trim();
      if (!choiceText || !target) return null;
      return { text: choiceText, target };
    })
    .filter((choice): choice is SceneChoice => Boolean(choice));
}

function sceneMetaByHeader(rawDesignText: string | null | undefined, plan: NarrativePlan | null, scenePlan: ScenePlan | null) {
  const mapping = scenePlanMetaByHeader(scenePlan, plan);
  if (!rawDesignText) return mapping;
  parseGameDesignDraft(rawDesignText, plan, scenePlan).forEach((scene) => {
    const strtype = storyStepStrtype(plan, scene.sourceNode);
    mapping.set(scene.header, {
      title: scene.title || mapping.get(scene.header)?.title || scene.header.replace(/\.txt$/i, "").replace(/_/g, " "),
      marker: scene.marker,
      sourceNode: scene.sourceNode,
      strtype: strtype || scene.strtype || mapping.get(scene.header)?.strtype || ""
    });
  });
  return mapping;
}

export function parseScenes(text: string, plan: NarrativePlan | null, rawDesignText?: string | null, scenePlan: ScenePlan | null = null): SceneDraft[] {
  const fromJson = scenesFromCompletedJson(text, plan, scenePlan);
  if (fromJson) return fromJson;
  const lines = text.split(/\r?\n/);
  const scenes: SceneDraft[] = [];
  let current: SceneDraft | null = null;
  const metaByHeader = sceneMetaByHeader(rawDesignText, plan, scenePlan);

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    const bracket = trimmed.match(/^\[([A-Za-z0-9_-]+\.txt)\]$/);
    const labelled = trimmed.match(/^(?:Scene|Ending)\s*[:：]\s*([A-Za-z0-9_-]+\.txt)$/i);
    const header = bracket?.[1] || labelled?.[1];
    if (header) {
      const meta = metaByHeader.get(header);
      current = {
        header,
        title: meta?.title || header.replace(/\.txt$/, "").replace(/_/g, " "),
        lines: [],
        marker: meta?.marker,
        sourceNode: meta?.sourceNode,
        strtype: meta?.strtype
      };
      scenes.push(current);
      return;
    }
    if (!current || !trimmed) return;
    current.lines.push(parseSceneLine(line, `${current.header}-${index}`));
  });

  return scenes;
}

function parseSceneLine(line: string, id: string): SceneLine {
  const original = line.trim();
  const choiceMatch = original.match(/^choose\s*[:：]\s*(.*)$/i);
  if (choiceMatch) {
    return { id, kind: "choice", speaker: "分支", text: "", rawPrefix: "choose", choices: parseChoiceOptions(choiceMatch[1]) };
  }

  const branchMatch = original.match(/^:([A-Za-z0-9_-]+)\s*;?$/);
  if (branchMatch) {
    return { id, kind: "branch", speaker: "分支", text: branchMatch[1], rawPrefix: "branch", branchLabel: branchMatch[1] };
  }

  const trimmed = original.replace(/^>\s*/, "");
  const narrationMatch = trimmed.match(/^(旁白|intro)\s*[:：]\s*(.*?);?$/);
  if (narrationMatch) {
    return { id, kind: "narration", speaker: "旁白", text: cleanEditableLineText(narrationMatch[2]), rawPrefix: narrationMatch[1] };
  }

  const dialogueMatch = trimmed.match(/^([^:：;]{1,24})[:：]\s*(.*)$/);
  if (dialogueMatch && !trimmed.startsWith("setVar:") && !trimmed.startsWith("change") && !trimmed.startsWith("choose:")) {
    return { id, kind: "dialogue", speaker: dialogueMatch[1], text: cleanEditableLineText(dialogueMatch[2]), rawPrefix: "" };
  }

  return { id, kind: "command", speaker: "指令", text: cleanEditableLineText(trimmed), rawPrefix: "" };
}

export function draftLineRows(text: string) {
  return Math.max(2, text.split(/\r?\n/).reduce((total, line) => total + Math.ceil(Math.max(line.length, 1) / 36), 0));
}
