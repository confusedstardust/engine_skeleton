"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

type Job = {
  id: string;
  status: string;
  phase?: string | null;
  error?: string | null;
};

type NodeArtifact = {
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

type NodesResponse = {
  job: Job;
  nodes: NodeArtifact[];
  scenes: NodeArtifact[];
};

type AssetReviewItem = {
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

type AssetReviewResponse = {
  job: Job;
  assets: AssetReviewItem[];
  image_enabled: boolean;
};

type StoryStep = {
  id: string;
  name: string;
  content: string;
  narrative_target: string;
  strtype: string;
};

type NarrativeCharacter = {
  id: string;
  name: string;
  gender: string;
  personality: string;
  motivation: string;
  speech_style: string;
  emotional_arc: string;
  relationships: { with: string; dynamic: string }[];
};

type NarrativeEnding = {
  ending_type: string;
  description: string;
};

type NarrativeNodeKind = "phase" | "ending" | "character";

type GeneratedNarrativeNodeResponse = {
  kind: NarrativeNodeKind;
  node: StoryStep | NarrativeEnding | NarrativeCharacter;
};

type SyncNarrativeStructureResponse = {
  narrative_plan: NarrativePlan;
  narrative_structure: string;
  issues: { node: string; reason: string }[];
};

type SyncNarrativeStructureOptions = {
  quiet?: boolean;
  force?: boolean;
};

type NarrativePlan = {
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

type ScenePlan = {
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

type SceneDraft = {
  header: string;
  title: string;
  lines: SceneLine[];
  marker?: "Scene" | "Ending";
  sourceNode?: string;
  strtype?: string;
};

type GameDesignDraftScene = SceneDraft & {
  marker: "Scene" | "Ending";
  sourceNode: string;
  endingType: string;
};

type SceneLine = {
  id: string;
  kind: "narration" | "dialogue" | "command" | "choice" | "branch";
  speaker: string;
  text: string;
  rawPrefix: string;
  choices?: SceneChoice[];
  branchLabel?: string;
};

type SceneChoice = {
  text: string;
  target: string;
  target_scene_file?: string;
  targetSceneFile?: string;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/forge${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

function compactId(id: string) {
  return `${id.slice(0, 8)}...${id.slice(-4)}`;
}

function parsePlan(content: string | null): NarrativePlan | null {
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

function parseFlowEdges(structure: string, plan: NarrativePlan) {
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

function flowNodes(plan: NarrativePlan) {
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

function parseScenePlan(content: string | null): ScenePlan | null {
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

type GameDesignJsonScene = Partial<GameDesignDraftScene> & {
  scene_file?: string;
  source_node?: string;
  ending_type?: string;
};

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

function serializeGameDesignJson(scenes: SceneDraft[]) {
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

function parseGameDesignDraft(text: string, plan: NarrativePlan | null, scenePlan: ScenePlan | null = null): GameDesignDraftScene[] {
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

function normalizeStrtype(strtype?: string) {
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

function draftSceneRouteLabel(scene: GameDesignDraftScene, plan: NarrativePlan | null) {
  const label = strtypeLabel(storyStepStrtype(plan, scene.sourceNode || scene.header.replace(/\.txt$/i, "")));
  if (label) return label;
  return scene.marker === "Ending" ? "结局" : "未标注";
}

function completedSceneRouteLabel(scene: SceneDraft) {
  return strtypeLabel(scene.strtype) || "未标注";
}

function sceneMarkerLabel(scene: Pick<SceneDraft, "marker">) {
  return scene.marker === "Ending" ? "结局" : "场景";
}

function choiceTargetValue(choice: SceneChoice) {
  return choice.target_scene_file || choice.targetSceneFile || choice.target || "";
}

function sceneTargetOptions(scenePlan: ScenePlan | null, plan: NarrativePlan | null, scenes: SceneDraft[], currentHeader?: string) {
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

type SceneMeta = {
  title: string;
  marker: "Scene" | "Ending";
  sourceNode: string;
  strtype: string;
};

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

function parseScenes(text: string, plan: NarrativePlan | null, rawDesignText?: string | null, scenePlan: ScenePlan | null = null): SceneDraft[] {
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

function draftLineRows(text: string) {
  return Math.max(2, text.split(/\r?\n/).reduce((total, line) => total + Math.ceil(Math.max(line.length, 1) / 36), 0));
}

export default function JobWorkspacePage() {
  const params = useParams<{ jobId: string }>();
  const jobId = Array.isArray(params.jobId) ? params.jobId[0] : params.jobId;
  const [data, setData] = useState<NodesResponse | null>(null);
  const [message, setMessage] = useState("正在读取任务...");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<"outline" | "scenes" | "assets">("outline");
  const [stageHydrated, setStageHydrated] = useState(false);
  const [plan, setPlan] = useState<NarrativePlan | null>(null);
  const [planDirty, setPlanDirty] = useState(false);
  const [flowSyncing, setFlowSyncing] = useState(false);
  const [phaseBrief, setPhaseBrief] = useState("");
  const [endingBrief, setEndingBrief] = useState("");
  const [characterBrief, setCharacterBrief] = useState("");
  const [pendingPhaseBrief, setPendingPhaseBrief] = useState("");
  const [pendingEndingBrief, setPendingEndingBrief] = useState("");
  const [pendingCharacterBrief, setPendingCharacterBrief] = useState("");
  const [outlineSubmitted, setOutlineSubmitted] = useState(false);
  const [scenes, setScenes] = useState<SceneDraft[]>([]);
  const [activeScene, setActiveScene] = useState(0);
  const [scenesDirty, setScenesDirty] = useState(false);
  const [designDraft, setDesignDraft] = useState("");
  const [designDraftScenes, setDesignDraftScenes] = useState<GameDesignDraftScene[]>([]);
  const [designDraftDirty, setDesignDraftDirty] = useState(false);
  const [assetReview, setAssetReview] = useState<AssetReviewResponse | null>(null);
  const [activeAssetFilename, setActiveAssetFilename] = useState<string | null>(null);
  const [assetPrompt, setAssetPrompt] = useState("");
  const planRef = useRef<NarrativePlan | null>(null);

  const narrativeNode = data?.nodes.find((node) => node.key === "narrative_plan");
  const rawDesignNode = data?.nodes.find((node) => node.key === "game_design");
  const scenePlanNode = data?.nodes.find((node) => node.key === "scene_plan");
  const designNode = data?.nodes.find((node) => node.key === "game_design_completed");
  const assetManifestNode = data?.nodes.find((node) => node.key === "asset_manifest");
  const scenePlanContent = scenePlanNode?.content || null;
  const scenePlan = useMemo(() => parseScenePlan(scenePlanContent), [scenePlanContent]);
  const isGenerating = data?.job.status === "RUNNING" || data?.job.status === "QUEUED";
  const assetPhases = new Set([
    "ASSET_REVIEW",
    "ASSET_PLANNING",
    "ASSET_GENERATION",
    "GAME_BUILD",
    "SCRIPT_REWRITE",
    "SOUND_EFFECT_PLANNING",
    "TTS_GENERATION",
    "SCENE_WRITING",
    "VALIDATING"
  ]);
  const inAssetOrBuildStage = Boolean(assetManifestNode?.exists) || Boolean(assetReview?.assets.length) || assetPhases.has(data?.job.phase || "") || data?.job.status === "DONE";
  const outlineLocked = outlineSubmitted || Boolean(designNode?.exists) || data?.job.phase === "GAME_DESIGN" || inAssetOrBuildStage;
  const scenesLocked = inAssetOrBuildStage;
  const canOpenScenes = outlineLocked || Boolean(rawDesignNode?.exists) || Boolean(designNode?.exists);
  const canOpenAssets = inAssetOrBuildStage;
  const activeAsset = assetReview?.assets.find((asset) => asset.filename === activeAssetFilename) || null;

  const refresh = useCallback(async (silent = false) => {
    if (!jobId) return;
    try {
      const next = await api<NodesResponse>(`/jobs/${jobId}/nodes`);
      setData(next);
      const review = await api<AssetReviewResponse>(`/jobs/${jobId}/assets/review`);
      setAssetReview(review);
      if (!silent) setMessage("任务内容已更新。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取任务失败。");
    }
  }, [jobId]);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(() => refresh(true), 2200);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!planDirty) {
      const parsed = parsePlan(narrativeNode?.content || null);
      if (parsed) setPlan(parsed);
    }
  }, [narrativeNode?.content, planDirty]);

  useEffect(() => {
    planRef.current = plan;
  }, [plan]);

  useEffect(() => {
    if (!scenesDirty && designNode?.content) {
      const parsed = parseScenes(designNode.content, plan, rawDesignNode?.content, scenePlan);
      setScenes(parsed);
      setActiveScene(0);
    }
  }, [designNode?.content, scenesDirty, plan, rawDesignNode?.content, scenePlan]);

  useEffect(() => {
    if (!designDraftDirty && rawDesignNode?.content) {
      setDesignDraft(rawDesignNode.content);
      setDesignDraftScenes(parseGameDesignDraft(rawDesignNode.content, plan, scenePlan));
    }
  }, [rawDesignNode?.content, designDraftDirty, plan, scenePlan]);

  useEffect(() => {
    if (!data || stageHydrated) return;
    if (canOpenAssets) setStage("assets");
    else if (canOpenScenes) setStage("scenes");
    setStageHydrated(true);
  }, [canOpenAssets, canOpenScenes, data, stageHydrated]);

  function updatePlan(next: NarrativePlan) {
    setPlan(next);
    planRef.current = next;
    setPlanDirty(true);
  }

  const syncNarrativeStructure = useCallback(async (targetPlan?: NarrativePlan | null, options: SyncNarrativeStructureOptions = {}) => {
    const nextTarget = targetPlan || planRef.current;
    if (!nextTarget || (outlineLocked && !options.force)) return;
    const snapshot = JSON.stringify(nextTarget);
    if (options.quiet) {
      setFlowSyncing(true);
    } else {
      setBusy(true);
      setMessage("正在同步流程图...");
    }
    try {
      const result = await api<SyncNarrativeStructureResponse>(`/jobs/${jobId}/narrative-structure/sync`, {
        method: "POST",
        body: JSON.stringify({ narrative_plan: nextTarget })
      });
      const latestPlan = planRef.current;
      const canApply = !options.quiet || JSON.stringify(latestPlan) === snapshot;
      if (canApply) {
        setPlan(result.narrative_plan);
        planRef.current = result.narrative_plan;
        setPlanDirty(false);
      }
      if (!options.quiet) {
        setMessage(result.issues.length > 0 ? "流程图已同步，但仍有节点需要检查。" : "流程图已同步。");
        await refresh(true);
      }
    } catch (error) {
      if (!options.quiet) {
        setMessage(error instanceof Error ? error.message : "同步流程图失败。");
      }
    } finally {
      if (options.quiet) {
        setFlowSyncing(false);
      } else {
        setBusy(false);
      }
    }
  }, [jobId, outlineLocked, refresh]);

  useEffect(() => {
    if (!plan || !planDirty || outlineLocked) return;
    const timer = window.setTimeout(() => {
      void syncNarrativeStructure(plan, { quiet: true });
    }, 900);
    return () => window.clearTimeout(timer);
  }, [outlineLocked, plan, planDirty, syncNarrativeStructure]);

  async function savePlan() {
    if (!plan) return;
    setBusy(true);
    setMessage("正在保存大纲并同步流程图...");
    try {
      const result = await api<SyncNarrativeStructureResponse>(`/jobs/${jobId}/narrative-structure/sync`, {
        method: "POST",
        body: JSON.stringify({ narrative_plan: plan })
      });
      setPlan(result.narrative_plan);
      planRef.current = result.narrative_plan;
      setPlanDirty(false);
      setMessage(result.issues.length > 0 ? "大纲已保存，流程图仍有节点需要检查。" : "大纲和流程图已保存。");
      await refresh(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存大纲失败。");
    } finally {
      setBusy(false);
    }
  }

  async function nextToScenes() {
    if (!plan) return;
    setBusy(true);
    setMessage("正在启动场景草稿生成...");
    try {
      if (planDirty) {
        const result = await api<SyncNarrativeStructureResponse>(`/jobs/${jobId}/narrative-structure/sync`, {
          method: "POST",
          body: JSON.stringify({ narrative_plan: plan })
        });
        setPlan(result.narrative_plan);
        planRef.current = result.narrative_plan;
        setPlanDirty(false);
      }
      await api<Job>(`/jobs/${jobId}/phases/game_design_draft`, {
        method: "POST",
        body: JSON.stringify({ background: true })
      });
      await refresh(true);
      setOutlineSubmitted(true);
      setStage("scenes");
      setMessage("场景设计稿正在生成，完成后可以先审阅 game_design.json。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "进入下一步失败。");
    } finally {
      setBusy(false);
    }
  }

  async function generateAndAppendNode(kind: NarrativeNodeKind, prompt: string) {
    if (!plan || outlineLocked) return;
    const brief = prompt.trim() || `新增${kind === "phase" ? "阶段" : kind === "ending" ? "结局" : "角色"}`;
    setBusy(true);
    if (kind === "phase") setPendingPhaseBrief(brief);
    if (kind === "ending") setPendingEndingBrief(brief);
    if (kind === "character") setPendingCharacterBrief(brief);
    try {
      const result = await api<GeneratedNarrativeNodeResponse>(`/jobs/${jobId}/narrative-node`, {
        method: "POST",
        body: JSON.stringify({ kind, prompt: brief, narrative_plan: plan })
      });
      const nextPlan: NarrativePlan =
        result.kind === "phase"
          ? { ...plan, story_progression: [...plan.story_progression, result.node as StoryStep] }
          : result.kind === "ending"
            ? { ...plan, endings: [...plan.endings, result.node as NarrativeEnding] }
            : { ...plan, characters: [...plan.characters, result.node as NarrativeCharacter] };
      const synced = await api<SyncNarrativeStructureResponse>(`/jobs/${jobId}/narrative-structure/sync`, {
        method: "POST",
        body: JSON.stringify({ narrative_plan: nextPlan })
      });
      setPlan(synced.narrative_plan);
      planRef.current = synced.narrative_plan;
      setPlanDirty(false);
      if (kind === "phase") setPhaseBrief("");
      if (kind === "ending") setEndingBrief("");
      if (kind === "character") setCharacterBrief("");
      setMessage(`新增${kind === "phase" ? "阶段" : kind === "ending" ? "结局" : "角色"}已保存，流程图已同步。`);
      await refresh(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "新增节点失败。");
    } finally {
      if (kind === "phase") setPendingPhaseBrief("");
      if (kind === "ending") setPendingEndingBrief("");
      if (kind === "character") setPendingCharacterBrief("");
      setBusy(false);
    }
  }

  function addPhase() {
    void generateAndAppendNode("phase", phaseBrief);
  }

  function addEnding() {
    void generateAndAppendNode("ending", endingBrief);
  }

  function addCharacter() {
    void generateAndAppendNode("character", characterBrief);
  }

  async function saveScenes() {
    setBusy(true);
    setMessage(scenesDirty ? "正在保存场景内容..." : "正在启动素材阶段...");
    try {
      if (scenesDirty) {
        await api(`/jobs/${jobId}/artifacts`, {
          method: "PATCH",
          body: JSON.stringify({ path: "state/game_design_completed.json", content: serializeGameDesignJson(scenes) })
        });
        setScenesDirty(false);
      }
      await api<Job>(`/jobs/${jobId}/phases/asset_review`, {
        method: "POST",
        body: JSON.stringify({ background: true })
      });
      setStage("assets");
      setMessage("素材规划和生成已启动，完成后可以审阅角色卡和场景卡。");
      await refresh(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "启动素材阶段失败。");
    } finally {
      setBusy(false);
    }
  }

  async function regenerateAsset(asset: AssetReviewItem, prompt: string) {
    setBusy(true);
    setMessage(`正在重新生成素材：${asset.filename}`);
    try {
      await api(`/jobs/${jobId}/assets/regenerate`, {
        method: "POST",
        body: JSON.stringify({ filename: asset.filename, prompt, background: true })
      });
      setMessage("单个素材已加入生成队列。");
      await refresh(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "重新生成素材失败。");
    } finally {
      setBusy(false);
    }
  }

  async function buildGameFromAssets() {
    setBusy(true);
    setMessage("正在改写 WebGAL 脚本并生成游戏...");
    try {
      await api<Job>(`/jobs/${jobId}/phases/game_build`, {
        method: "POST",
        body: JSON.stringify({ background: true })
      });
      setMessage("游戏生成已启动，完成后可以点击右上角打开游戏。");
      await refresh(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成游戏失败。");
    } finally {
      setBusy(false);
    }
  }

  async function saveDesignDraft() {
    setBusy(true);
    setMessage("正在保存场景设计稿...");
    try {
      await api(`/jobs/${jobId}/artifacts`, {
        method: "PATCH",
        body: JSON.stringify({ path: "state/game_design.json", content: designDraft })
      });
      setDesignDraftDirty(false);
      setMessage("场景设计稿已保存。");
      await refresh(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存场景设计稿失败。");
    } finally {
      setBusy(false);
    }
  }

  async function completeDesignDraft() {
    setBusy(true);
    setMessage("正在根据场景设计稿生成详细旁白和对话...");
    try {
      if (designDraftDirty) {
        await api(`/jobs/${jobId}/artifacts`, {
          method: "PATCH",
          body: JSON.stringify({ path: "state/game_design.json", content: designDraft })
        });
        setDesignDraftDirty(false);
      }
      await api<Job>(`/jobs/${jobId}/phases/game_design_completion`, {
        method: "POST",
        body: JSON.stringify({ background: true })
      });
      await refresh(true);
      setMessage("详细场景正在生成，完成后可以逐个场景审阅旁白和对话。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成详细场景失败。");
    } finally {
      setBusy(false);
    }
  }

  function updateScene(index: number, next: SceneDraft) {
    setScenes((current) => current.map((scene, sceneIndex) => (sceneIndex === index ? next : scene)));
    setScenesDirty(true);
  }

  function updateDesignDraftScenes(next: GameDesignDraftScene[]) {
    setDesignDraftScenes(next);
    setDesignDraft(serializeGameDesignJson(next));
    setDesignDraftDirty(true);
  }

  if (!data) {
    return (
      <main className="main-wrapper">
        <section className="workspace-empty">
          <h1>生成工作台</h1>
          <p>{message}</p>
        </section>
      </main>
    );
  }

  return (
    <>
      <header className="top-nav">
        <Link className="brand brand-link" href="/">
          <div className="brand-seal">文</div>
          <div className="brand-copy">
            <span className="brand-name">文境 · 生成工作台</span>
            <span className="brand-subtitle">JOB {compactId(data.job.id)}</span>
          </div>
        </Link>
        <nav className="nav-links" aria-label="任务导航">
          <Link href="/">新建任务</Link>
          {data.job.status === "DONE" && <a className="nav-login" href={`/play/${data.job.id}/`} target="_blank">打开游戏</a>}
        </nav>
      </header>

      <main className="main-wrapper workspace-wrapper">
        <section className="workflow-head">
          <div>
            <span className={`status-pill ${data.job.status.toLowerCase()}`}>{data.job.status}</span>
            <h1>{stage === "outline" ? "确认故事大纲" : stage === "scenes" ? "审阅场景文本" : "审阅素材资产"}</h1>
            <p>
              {stage === "outline"
                ? "先确认阶段数量和角色阵容。这里的删改会影响下一阶段生成的场景。"
                : stage === "scenes"
                  ? "按场景逐个审阅旁白、对话和分支内容，保存后会进入素材规划和生成。"
                  : "按角色和场景检查素材规划、生成图片和提示词，不满意的单个资产可以重新生成。"}
            </p>
          </div>
          <div className="workflow-steps">
            <button className={stage === "outline" ? "active" : ""} type="button" onClick={() => setStage("outline")}>1 大纲</button>
            <button className={stage === "scenes" ? "active" : ""} type="button" onClick={() => setStage("scenes")} disabled={!canOpenScenes}>2 场景</button>
            <button className={stage === "assets" ? "active" : ""} type="button" onClick={() => setStage("assets")} disabled={!canOpenAssets}>3 素材</button>
          </div>
        </section>

        <div className="workspace-status workflow-status">
          <strong>{data.job.phase || "等待中"}</strong>
          <span>{data.job.error || message}</span>
        </div>

        {stage === "outline" ? (
          <OutlineEditor
            plan={plan}
            busy={busy || isGenerating}
            planDirty={planDirty}
            flowSyncing={flowSyncing}
            locked={outlineLocked}
            phaseBrief={phaseBrief}
            endingBrief={endingBrief}
            characterBrief={characterBrief}
            pendingPhaseBrief={pendingPhaseBrief}
            pendingEndingBrief={pendingEndingBrief}
            pendingCharacterBrief={pendingCharacterBrief}
            setPhaseBrief={setPhaseBrief}
            setEndingBrief={setEndingBrief}
            setCharacterBrief={setCharacterBrief}
            updatePlan={updatePlan}
            addPhase={addPhase}
            addEnding={addEnding}
            addCharacter={addCharacter}
            savePlan={savePlan}
            syncStructure={syncNarrativeStructure}
            nextToScenes={nextToScenes}
          />
        ) : stage === "assets" ? (
          <AssetReviewPanel
            review={assetReview}
            busy={busy || isGenerating}
            activeAsset={activeAsset}
            assetPrompt={assetPrompt}
            setAssetPrompt={setAssetPrompt}
            openAsset={(asset) => {
              setActiveAssetFilename(asset.filename);
              setAssetPrompt(asset.prompt || "");
            }}
            closeAsset={() => setActiveAssetFilename(null)}
            regenerateAsset={regenerateAsset}
            buildGame={buildGameFromAssets}
            gameReady={data.job.status === "DONE"}
            playUrl={`/play/${data.job.id}/`}
          />
        ) : designNode?.exists ? (
          <SceneEditor
            plan={plan}
            scenePlan={scenePlan}
            scenes={scenes}
            activeScene={activeScene}
            busy={busy || isGenerating}
            readonly={scenesLocked}
            scenesDirty={scenesDirty}
            setActiveScene={setActiveScene}
            updateScene={updateScene}
            setScenes={setScenes}
            setScenesDirty={setScenesDirty}
            saveScenes={saveScenes}
          />
        ) : (
          <DesignDraftEditor
            plan={plan}
            scenes={designDraftScenes}
            exists={Boolean(rawDesignNode?.exists)}
            busy={busy || isGenerating}
            dirty={designDraftDirty}
            onChange={updateDesignDraftScenes}
            saveDesignDraft={saveDesignDraft}
            completeDesignDraft={completeDesignDraft}
          />
        )}
      </main>
    </>
  );
}

function AssetReviewPanel(props: {
  review: AssetReviewResponse | null;
  busy: boolean;
  activeAsset: AssetReviewItem | null;
  assetPrompt: string;
  setAssetPrompt: (value: string) => void;
  openAsset: (asset: AssetReviewItem) => void;
  closeAsset: () => void;
  regenerateAsset: (asset: AssetReviewItem, prompt: string) => Promise<void>;
  buildGame: () => Promise<void>;
  gameReady: boolean;
  playUrl: string;
}) {
  const assets = props.review?.assets || [];
  const figures = assets.filter((asset) => asset.kind === "角色立绘");
  const backgrounds = assets.filter((asset) => asset.kind !== "角色立绘");
  const hasGeneratedImages = assets.some((asset) => asset.exists);

  if (!props.review || assets.length === 0) {
    return (
      <section className="node-detail">
        <LoadingPlaceholder
          title="素材规划还在生成。"
          brief="场景保存后会自动进入素材阶段，完成后这里会展示角色卡和场景卡。"
        />
      </section>
    );
  }

  return (
    <section className="node-detail">
      <div className="node-detail-head">
        <div>
          <h2>素材审阅</h2>
          <p>
            {props.review.image_enabled
              ? "图片生成开启时，生成完成的素材会显示预览；点击卡片可以查看大图、立绘和 prompt。"
              : "当前任务未开启图片生成，因此这里展示素材规划和 prompt，后续仍可单独生成指定素材。"}
          </p>
        </div>
        <div className="asset-review-controls">
          <div className="asset-summary">
            <span>{figures.length} 个角色</span>
            <span>{backgrounds.length} 个场景</span>
            <span>{hasGeneratedImages ? "已有图片" : "等待图片"}</span>
          </div>
          <div className="node-actions">
            {props.gameReady ? (
              <a className="btn primary" href={props.playUrl} target="_blank">打开游戏</a>
            ) : (
              <button className="btn primary" type="button" disabled={props.busy || assets.length === 0} onClick={() => void props.buildGame()}>
                确认素材并生成游戏
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="asset-review-grid">
        <AssetGroup title="角色卡" assets={figures} openAsset={props.openAsset} />
        <AssetGroup title="场景卡" assets={backgrounds} openAsset={props.openAsset} />
      </div>

      {props.activeAsset && (
        <div className="asset-modal-layer">
          <button className="asset-modal-dismiss" type="button" aria-label="关闭素材预览" onClick={props.closeAsset} />
          <article className="asset-modal">
            <div className="asset-modal-media">
              {props.activeAsset.exists ? (
                <Image src={props.activeAsset.url} alt={props.activeAsset.filename} width={960} height={540} unoptimized />
              ) : (
                <div className="asset-image-placeholder">图片尚未生成</div>
              )}
              {props.activeAsset.avatar_exists && props.activeAsset.avatar_url && (
                <div className="asset-avatar-preview">
                  <span>头像</span>
                  <Image src={props.activeAsset.avatar_url} alt={`${props.activeAsset.filename} 头像`} width={88} height={88} unoptimized />
                </div>
              )}
            </div>
            <div className="asset-modal-body">
              <span>{props.activeAsset.kind}</span>
              <h3>{assetDisplayName(props.activeAsset)}</h3>
              <dl>
                <div>
                  <dt>文件</dt>
                  <dd>{props.activeAsset.subdir}/{props.activeAsset.filename}.webp</dd>
                </div>
                <div>
                  <dt>尺寸</dt>
                  <dd>{props.activeAsset.size || "未设置"}</dd>
                </div>
                <div>
                  <dt>对应场景</dt>
                  <dd>{assetSceneDisplayName(props.activeAsset)}</dd>
                </div>
              </dl>
              <label className="asset-prompt-editor">
                <span>Prompt</span>
                <textarea
                  value={props.assetPrompt}
                  onChange={(event) => props.setAssetPrompt(event.target.value)}
                  rows={9}
                  spellCheck={false}
                />
              </label>
              <div className="asset-modal-actions">
                <button className="btn outline" type="button" onClick={props.closeAsset}>关闭</button>
                <button
                  className="btn primary"
                  type="button"
                  disabled={props.busy}
                  onClick={() => void props.regenerateAsset(props.activeAsset as AssetReviewItem, props.assetPrompt)}
                >
                  重新生成此素材
                </button>
              </div>
            </div>
          </article>
        </div>
      )}
    </section>
  );
}

function AssetGroup(props: { title: string; assets: AssetReviewItem[]; openAsset: (asset: AssetReviewItem) => void }) {
  return (
    <section className="asset-group">
      <div className="asset-group-head">
        <h3>{props.title}</h3>
        <span>{props.assets.length}</span>
      </div>
      {props.assets.length === 0 ? (
        <div className="asset-empty">暂无素材</div>
      ) : (
        <div className="asset-card-grid">
          {props.assets.map((asset) => (
            <button className="asset-card" key={`${asset.subdir}-${asset.filename}`} type="button" onClick={() => props.openAsset(asset)}>
              <div className="asset-thumb">
                {asset.exists ? <Image src={asset.url} alt={asset.filename} width={320} height={180} unoptimized /> : <span>待生成</span>}
              </div>
              <div>
                <strong>{assetDisplayName(asset)}</strong>
                <small>{assetSceneDisplayName(asset)}</small>
              </div>
              <em className={asset.exists ? "ready" : ""}>{asset.exists ? "已生成" : "待生成"}</em>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function assetDisplayName(asset: AssetReviewItem) {
  if (asset.display_name) return asset.display_name;
  return asset.filename
    .replace(/^figure_/, "")
    .replace(/^bg_/, "")
    .replace(/^title_/, "")
    .replace(/_/g, " ");
}

function assetSceneDisplayName(asset: AssetReviewItem) {
  return asset.scene_display_name || asset.available_scene || "通用";
}

function OutlineEditor(props: {
  plan: NarrativePlan | null;
  busy: boolean;
  planDirty: boolean;
  flowSyncing: boolean;
  locked: boolean;
  phaseBrief: string;
  endingBrief: string;
  characterBrief: string;
  pendingPhaseBrief: string;
  pendingEndingBrief: string;
  pendingCharacterBrief: string;
  setPhaseBrief: (value: string) => void;
  setEndingBrief: (value: string) => void;
  setCharacterBrief: (value: string) => void;
  updatePlan: (plan: NarrativePlan) => void;
  addPhase: () => void;
  addEnding: () => void;
  addCharacter: () => void;
  savePlan: () => void;
  syncStructure: (targetPlan?: NarrativePlan | null, options?: SyncNarrativeStructureOptions) => Promise<void>;
  nextToScenes: () => void;
}) {
  const [showFlowModal, setShowFlowModal] = useState(false);
  const { plan } = props;
  function openFlowPreview() {
    if (props.planDirty && !props.locked && !props.busy) {
      void props.syncStructure(plan, { quiet: true });
    }
    setShowFlowModal(true);
  }
  if (!plan) {
    return (
      <section className="node-detail">
        <LoadingPlaceholder
          title="故事大纲还没有生成完成。"
          brief="页面会自动刷新，大纲出现后就可以开始审阅。"
        />
      </section>
    );
  }

  return (
    <section className={`outline-workbench ${props.locked ? "readonly" : ""}`}>
      <div className="outline-main">
        {props.locked && (
          <div className="readonly-banner">大纲已确认，当前为只读状态。需要调整时请重新创建任务或回到确认前的任务。</div>
        )}
        <section className="review-section">
          <div className="review-section-head">
            <div>
              <h2>故事阶段</h2>
              <p>可以删除过多阶段，也可以简述想补充的阶段后加入列表。</p>
            </div>
            <span>{plan.story_progression.length} 个阶段</span>
          </div>
          <div className="brief-row">
            <input disabled={props.locked || props.busy} value={props.phaseBrief} onChange={(event) => props.setPhaseBrief(event.target.value)} placeholder="例如：增加一个暴露核心矛盾的转折阶段" />
            <button className="btn outline" type="button" disabled={props.locked || props.busy} onClick={props.addPhase}>添加阶段</button>
          </div>
          <div className="phase-editor-list">
            {props.pendingPhaseBrief && <PendingCard title="正在生成阶段" brief={props.pendingPhaseBrief} />}
            {plan.story_progression.map((step, index) => (
              <article className="phase-editor" key={`${step.id}-${index}`}>
                <div className="phase-editor-top">
                  <span>{step.id || `phase${index}`}</span>
                  <select
                    value={step.strtype || "main"}
                    onChange={(event) => {
                      const next = [...plan.story_progression];
                      next[index] = { ...step, strtype: event.target.value };
                      props.updatePlan({ ...plan, story_progression: next });
                    }}
                  >
                    <option value="main">主线</option>
                    <option value="branch">分支</option>
                  </select>
                  <button type="button" onClick={() => props.updatePlan({ ...plan, story_progression: plan.story_progression.filter((_, itemIndex) => itemIndex !== index) })}>删除</button>
                </div>
                <input
                  value={step.name}
                  onChange={(event) => {
                    const next = [...plan.story_progression];
                    next[index] = { ...step, name: event.target.value };
                    props.updatePlan({ ...plan, story_progression: next });
                  }}
                  placeholder="阶段名称"
                />
                <textarea
                  value={step.content}
                  onChange={(event) => {
                    const next = [...plan.story_progression];
                    next[index] = { ...step, content: event.target.value };
                    props.updatePlan({ ...plan, story_progression: next });
                  }}
                  placeholder="阶段内容"
                />
                <textarea
                  className="compact-textarea"
                  value={step.narrative_target}
                  onChange={(event) => {
                    const next = [...plan.story_progression];
                    next[index] = { ...step, narrative_target: event.target.value };
                    props.updatePlan({ ...plan, story_progression: next });
                  }}
                  placeholder="叙事目标"
                />
              </article>
            ))}
          </div>
        </section>

        <section className="review-section">
          <div className="review-section-head">
            <div>
              <h2>结局节点</h2>
              <p>结局会在下一步生成独立场景，也需要在大纲阶段一起确认。</p>
            </div>
            <span>{plan.endings.length} 个结局</span>
          </div>
          <div className="brief-row">
            <input disabled={props.locked || props.busy} value={props.endingBrief} onChange={(event) => props.setEndingBrief(event.target.value)} placeholder="例如：增加一个因没有完成关键选择而触发的遗憾结局" />
            <button className="btn outline" type="button" disabled={props.locked || props.busy} onClick={props.addEnding}>添加结局</button>
          </div>
          <div className="phase-editor-list">
            {props.pendingEndingBrief && <PendingCard title="正在生成结局" brief={props.pendingEndingBrief} />}
            {plan.endings.map((ending, index) => (
              <article className="phase-editor" key={`${ending.ending_type}-${index}`}>
                <div className="phase-editor-top">
                  <span>ending {index + 1}</span>
                  <button type="button" onClick={() => props.updatePlan({ ...plan, endings: plan.endings.filter((_, itemIndex) => itemIndex !== index) })}>删除</button>
                </div>
                <input
                  value={ending.ending_type}
                  onChange={(event) => {
                    const next = [...plan.endings];
                    next[index] = { ...ending, ending_type: event.target.value };
                    props.updatePlan({ ...plan, endings: next });
                  }}
                  placeholder="结局类型"
                />
                <textarea
                  value={ending.description}
                  onChange={(event) => {
                    const next = [...plan.endings];
                    next[index] = { ...ending, description: event.target.value };
                    props.updatePlan({ ...plan, endings: next });
                  }}
                  placeholder="结局描述"
                />
              </article>
            ))}
          </div>
        </section>

        <section className="review-section">
          <div className="review-section-head">
            <div>
              <h2>角色信息</h2>
              <p>可以增删角色，也可以先写一句补充说明，再在卡片中细化。</p>
            </div>
            <span>{plan.characters.length} 个角色</span>
          </div>
          <div className="brief-row">
            <input disabled={props.locked || props.busy} value={props.characterBrief} onChange={(event) => props.setCharacterBrief(event.target.value)} placeholder="例如：增加一个代表现实压力的反对者角色" />
            <button className="btn outline" type="button" disabled={props.locked || props.busy} onClick={props.addCharacter}>添加角色</button>
          </div>
          <div className="character-editor-grid">
            {props.pendingCharacterBrief && <PendingCard title="正在生成角色" brief={props.pendingCharacterBrief} />}
            {plan.characters.map((character, index) => (
              <article className="character-editor" key={`${character.id}-${index}`}>
                <div className="phase-editor-top">
                  <span>{character.id}</span>
                  <button type="button" onClick={() => props.updatePlan({ ...plan, characters: plan.characters.filter((_, itemIndex) => itemIndex !== index) })}>删除</button>
                </div>
                <input
                  value={character.name}
                  onChange={(event) => {
                    const next = [...plan.characters];
                    next[index] = { ...character, name: event.target.value };
                    props.updatePlan({ ...plan, characters: next });
                  }}
                  placeholder="角色名称"
                />
                <textarea
                  value={character.personality}
                  onChange={(event) => {
                    const next = [...plan.characters];
                    next[index] = { ...character, personality: event.target.value };
                    props.updatePlan({ ...plan, characters: next });
                  }}
                  placeholder="性格"
                />
                <textarea
                  className="compact-textarea"
                  value={character.motivation}
                  onChange={(event) => {
                    const next = [...plan.characters];
                    next[index] = { ...character, motivation: event.target.value };
                    props.updatePlan({ ...plan, characters: next });
                  }}
                  placeholder="动机"
                />
              </article>
            ))}
          </div>
        </section>
      </div>

      <aside className="outline-side">
        <div>
          <span>标题</span>
          <strong>{plan.title || "未命名"}</strong>
        </div>
        <div>
          <span>主题</span>
          <p>{plan.theme || "未填写"}</p>
        </div>
        <div>
          <span>故事弧</span>
          <p>{plan.story_arc || "未填写"}</p>
        </div>
        <button className="btn outline" type="button" disabled={props.locked || props.busy || !props.planDirty} onClick={props.savePlan}>保存大纲</button>
        <button className="btn outline" type="button" onClick={openFlowPreview}>
          查看流程图
        </button>
        <span className="flow-sync-note">{props.flowSyncing ? "流程图自动同步中..." : props.planDirty ? "修改后会自动同步流程图" : "流程图已同步"}</span>
        <button className="btn primary" type="button" disabled={props.locked || props.busy} onClick={props.nextToScenes}>
          {props.locked ? "大纲已确认" : "确认并生成下一步"}
        </button>
      </aside>
      {showFlowModal && (
        <div className="flow-modal-layer" role="dialog" aria-modal="true" aria-label="故事流程图">
          <button className="flow-modal-dismiss" type="button" aria-label="关闭流程图" onClick={() => setShowFlowModal(false)} />
          <section className="flow-modal">
            <div className="flow-modal-head">
              <div>
                <span>{props.flowSyncing ? "同步中" : "自动同步"}</span>
                <h3>故事流程图</h3>
              </div>
              <button className="btn outline" type="button" onClick={() => setShowFlowModal(false)}>关闭</button>
            </div>
            <div className="flow-modal-body">
              <NarrativeFlowPreview plan={plan} />
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

function NarrativeFlowPreview({ plan }: { plan: NarrativePlan }) {
  const nodes = flowNodes(plan);
  const edges = parseFlowEdges(plan.narrative_structure || "", plan);
  const reactId = useId();
  const renderId = useMemo(() => `narrative-flow-${reactId.replace(/[^A-Za-z0-9_-]/g, "")}`, [reactId]);
  const [svg, setSvg] = useState("");
  const [renderError, setRenderError] = useState("");
  const source = plan.narrative_structure?.trim() || "";

  useEffect(() => {
    let cancelled = false;
    if (!source) {
      setSvg("");
      setRenderError("");
      return;
    }

    async function renderMermaid() {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          themeVariables: {
            background: "#fffdf8",
            primaryColor: "#fff8ef",
            primaryBorderColor: "#d8c8aa",
            primaryTextColor: "#2d2924",
            lineColor: "#9b2335",
            secondaryColor: "#f5eee2",
            tertiaryColor: "#f9f4ec",
            fontFamily: "STSong, SimSun, serif"
          }
        });
        const result = await mermaid.render(renderId, source);
        if (!cancelled) {
          setSvg(result.svg);
          setRenderError("");
        }
      } catch (error) {
        if (!cancelled) {
          setSvg("");
          setRenderError(error instanceof Error ? error.message : "流程图渲染失败。");
        }
      }
    }

    void renderMermaid();
    return () => {
      cancelled = true;
    };
  }, [renderId, source]);

  return (
    <section className="flow-preview">
      <div className="flow-preview-head">
        <span>Mermaid 流程图</span>
        <strong>{nodes.length} 个节点</strong>
      </div>

      <div className="flow-mermaid-canvas">
        {!source ? (
          <p>暂无流程图内容，点击“同步流程图”生成。</p>
        ) : svg ? (
          <div className="flow-mermaid-svg" dangerouslySetInnerHTML={{ __html: svg }} />
        ) : (
          <p>{renderError || "正在渲染流程图..."}</p>
        )}
      </div>

      {renderError && (
        <div className="flow-edge-list">
          {edges.length === 0 ? (
            <p>当前 Mermaid 文本暂时无法解析，也没有可展示的连线。</p>
          ) : (
            edges.map((edge, index) => (
              <div className="flow-edge" key={`${edge.source}-${edge.target}-${index}`}>
                <span>{edge.source}</span>
                <b aria-hidden="true">→</b>
                <span>{edge.target}</span>
              </div>
            ))
          )}
        </div>
      )}

      <div className="flow-node-list">
        {nodes.map((node) => (
          <div className="flow-node" key={node.id}>
            <span>{node.meta}</span>
            <strong>{node.label}</strong>
          </div>
        ))}
      </div>
      <div className="flow-character-strip">
        {plan.characters.map((character) => (
          <span key={character.id || character.name}>{character.name || character.id}</span>
        ))}
      </div>
    </section>
  );
}

function PendingCard({ title, brief }: { title: string; brief: string }) {
  return (
    <article className="phase-editor pending-card">
      <div className="pending-spinner" aria-hidden="true" />
      <strong>{title}</strong>
      <p>{brief}</p>
    </article>
  );
}

function LoadingPlaceholder({ title, brief }: { title: string; brief: string }) {
  return (
    <div className="node-placeholder loading">
      <div className="pending-spinner" aria-hidden="true" />
      <strong>{title}</strong>
      <span>{brief}</span>
    </div>
  );
}

function DesignDraftEditor(props: {
  plan: NarrativePlan | null;
  scenes: GameDesignDraftScene[];
  exists: boolean;
  busy: boolean;
  dirty: boolean;
  onChange: (scenes: GameDesignDraftScene[]) => void;
  saveDesignDraft: () => void;
  completeDesignDraft: () => void;
}) {
  const [speakerMenu, setSpeakerMenu] = useState<string | null>(null);
  const [activeDraftScene, setActiveDraftScene] = useState(0);
  const speakers = ["旁白", ...(props.plan?.characters.map((character) => character.name).filter(Boolean) || [])];
  const activeSceneIndex = Math.min(activeDraftScene, Math.max(props.scenes.length - 1, 0));
  const activeScene = props.scenes[activeSceneIndex];

  useEffect(() => {
    if (activeDraftScene > Math.max(props.scenes.length - 1, 0)) {
      setActiveDraftScene(Math.max(props.scenes.length - 1, 0));
    }
    setSpeakerMenu(null);
  }, [activeDraftScene, props.scenes.length]);

  function updateLine(sceneIndex: number, lineIndex: number, nextLine: SceneLine) {
    const nextScenes = props.scenes.map((scene, currentSceneIndex) => {
      if (currentSceneIndex !== sceneIndex) return scene;
      return {
        ...scene,
        lines: scene.lines.map((line, currentLineIndex) => (currentLineIndex === lineIndex ? nextLine : line))
      };
    });
    props.onChange(nextScenes);
  }

  function switchSpeaker(sceneIndex: number, lineIndex: number, speaker: string) {
    const line = props.scenes[sceneIndex].lines[lineIndex];
    updateLine(sceneIndex, lineIndex, {
      ...line,
      kind: speaker === "旁白" ? "narration" : "dialogue",
      speaker,
      rawPrefix: speaker === "旁白" ? "intro" : ""
    });
    setSpeakerMenu(null);
  }

  if (!props.exists) {
    return (
      <section className="node-detail">
        <LoadingPlaceholder
          title="场景设计稿还在生成。"
          brief="生成完成后，这里会按场景卡片展示，确认后再生成详细旁白和对话。"
        />
      </section>
    );
  }

  if (!activeScene) {
    return (
      <section className="node-detail">
        <div className="node-placeholder">
          <strong>场景设计稿还没有可展示的场景。</strong>
          <span>请稍后刷新，或回到大纲重新生成场景设计稿。</span>
        </div>
      </section>
    );
  }

  return (
    <section className="node-detail">
      {speakerMenu && <button className="speaker-dismiss-layer" type="button" aria-label="关闭角色菜单" onClick={() => setSpeakerMenu(null)} />}
      <div className="node-detail-head">
        <div>
          <h2>场景设计稿</h2>
          <p>先按阶段和结局审阅场景结构、旁白、对白与互动安排，确认后再生成详细旁白与对话。</p>
        </div>
        <div className="node-actions">
          <button className="btn outline" type="button" disabled={props.busy || !props.dirty} onClick={props.saveDesignDraft}>保存设计稿</button>
          <button className="btn primary" type="button" disabled={props.busy || props.scenes.length === 0} onClick={props.completeDesignDraft}>确认并生成详细场景</button>
        </div>
      </div>

      <div className="draft-scene-tabs" aria-label="场景与结局列表">
        {props.scenes.map((scene, sceneIndex) => (
          <button
            className={sceneIndex === activeSceneIndex ? "active" : ""}
            key={`${scene.header}-${sceneIndex}`}
            type="button"
            onClick={() => setActiveDraftScene(sceneIndex)}
          >
            <span>{scene.marker === "Ending" ? "结局" : "场景"}</span>
            {scene.title}
          </button>
        ))}
      </div>

      <div className="draft-scene-stack">
          <article className="draft-scene-card" key={`${activeScene.header}-${activeSceneIndex}`}>
            <div className="draft-scene-card-head">
              <span>{activeScene.marker === "Ending" ? "结局" : "场景"}</span>
              <div className="draft-scene-title-wrap">
                <h3>{activeScene.title}</h3>
                <em>{draftSceneRouteLabel(activeScene, props.plan)}</em>
              </div>
            </div>

            <div className="draft-line-stack">
              {activeScene.lines.map((line, lineIndex) => {
                const menuKey = `${activeSceneIndex}-${lineIndex}`;
                return (
                  <div className={`draft-line ${line.kind} ${speakerMenu === menuKey ? "menu-open" : ""}`} key={line.id}>
                    <div className="draft-speaker-wrap">
                      <button className={`draft-speaker ${line.kind === "command" ? "static" : ""}`} type="button" onClick={() => setSpeakerMenu(speakerMenu === menuKey ? null : menuKey)}>
                        {line.kind === "narration" || line.kind === "command" ? "旁白" : line.speaker}
                      </button>
                      {speakerMenu === menuKey && (
                        <div className="speaker-popover">
                          {speakers.map((speaker) => (
                            <button key={speaker} type="button" onClick={() => switchSpeaker(activeSceneIndex, lineIndex, speaker)}>
                              {speaker}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                    <textarea
                      value={line.text}
                      rows={draftLineRows(line.text)}
                      onChange={(event) => updateLine(activeSceneIndex, lineIndex, { ...line, text: event.target.value })}
                      spellCheck={false}
                      aria-label={`${activeScene.title} ${line.kind === "narration" || line.kind === "command" ? "旁白" : line.speaker}`}
                    />
                  </div>
                );
              })}
            </div>
          </article>
      </div>
    </section>
  );
}

function SceneEditor(props: {
  plan: NarrativePlan | null;
  scenePlan: ScenePlan | null;
  scenes: SceneDraft[];
  activeScene: number;
  busy: boolean;
  readonly: boolean;
  scenesDirty: boolean;
  setActiveScene: (index: number) => void;
  updateScene: (index: number, scene: SceneDraft) => void;
  setScenes: React.Dispatch<React.SetStateAction<SceneDraft[]>>;
  setScenesDirty: (value: boolean) => void;
  saveScenes: () => void;
}) {
  const scene = props.scenes[props.activeScene];
  const [speakerMenu, setSpeakerMenu] = useState<string | null>(null);
  const speakers = ["旁白", ...(props.plan?.characters.map((character) => character.name).filter(Boolean) || [])];

  useEffect(() => {
    setSpeakerMenu(null);
  }, [props.activeScene]);

  const targetOptions = useMemo(
    () => sceneTargetOptions(props.scenePlan, props.plan, props.scenes, scene?.header),
    [props.scenePlan, props.plan, props.scenes, scene?.header]
  );
  const defaultChoiceTarget = targetOptions[0]?.file || "new_branch";

  function updateLine(lineIndex: number, nextLine: SceneLine) {
    if (!scene || props.readonly) return;
    const nextLines = [...scene.lines];
    nextLines[lineIndex] = nextLine;
    props.updateScene(props.activeScene, { ...scene, lines: nextLines });
  }

  function updateChoice(lineIndex: number, choiceIndex: number, nextChoice: SceneChoice) {
    if (!scene || props.readonly) return;
    const line = scene.lines[lineIndex];
    const choices = [...(line.choices || [])];
    choices[choiceIndex] = nextChoice;
    updateLine(lineIndex, { ...line, choices });
  }

  function updateChoiceTarget(lineIndex: number, choiceIndex: number, choice: SceneChoice, target: string) {
    updateChoice(lineIndex, choiceIndex, {
      ...choice,
      target,
      target_scene_file: /\.txt$/i.test(target) ? target : undefined
    });
  }

  function addLine(kind: "narration" | "dialogue") {
    if (!scene || props.readonly) return;
    const nextLine: SceneLine = {
      id: `${scene.header}-${Date.now()}`,
      kind,
      speaker: kind === "dialogue" ? "角色" : "旁白",
      text: kind === "dialogue" ? "新的对话内容" : "新的旁白内容",
      rawPrefix: "旁白"
    };
    props.updateScene(props.activeScene, { ...scene, lines: [...scene.lines, nextLine] });
  }

  function switchSpeaker(lineIndex: number, speaker: string) {
    if (!scene || props.readonly) return;
    const line = scene.lines[lineIndex];
    updateLine(lineIndex, {
      ...line,
      kind: speaker === "旁白" ? "narration" : "dialogue",
      speaker,
      rawPrefix: speaker === "旁白" ? "intro" : ""
    });
    setSpeakerMenu(null);
  }

  if (!scene) {
    return (
      <section className="node-detail">
        <LoadingPlaceholder
          title="详细场景还在生成。"
          brief="生成完成后，这里会按场景展示旁白、对白和分支内容。"
        />
      </section>
    );
  }

  return (
    <section className={`node-detail ${props.readonly ? "readonly" : ""}`}>
      {speakerMenu && <button className="speaker-dismiss-layer" type="button" aria-label="关闭角色菜单" onClick={() => setSpeakerMenu(null)} />}
      <div className="node-detail-head">
        <div>
          <h2>详细场景</h2>
          <p>{props.readonly ? "素材阶段已开始，场景内容已锁定为只读状态。" : "按场景审阅旁白、对白和分支内容；分支会插入在正文中，并用 △ 标识。"}</p>
        </div>
        {!props.readonly && (
          <div className="node-actions">
            <button className="btn outline" type="button" onClick={() => addLine("narration")}>添加旁白</button>
            <button className="btn outline" type="button" onClick={() => addLine("dialogue")}>添加对话</button>
            <button className="btn primary" type="button" disabled={props.busy} onClick={props.saveScenes}>保存并生成素材</button>
          </div>
        )}
      </div>

      <div className="draft-scene-tabs" aria-label="场景列表">
        {props.scenes.map((item, index) => (
          <button className={props.activeScene === index ? "active" : ""} key={item.header} type="button" onClick={() => props.setActiveScene(index)}>
            <span>{sceneMarkerLabel(item)}</span>
            {item.title}
          </button>
        ))}
      </div>

      <div className="draft-scene-stack">
        <article className="draft-scene-card" key={`${scene.header}-${props.activeScene}`}>
          <div className="draft-scene-card-head">
            <span>{sceneMarkerLabel(scene)}</span>
            <div className="draft-scene-title-wrap editable">
              <input
                value={scene.title}
                onChange={(event) => props.updateScene(props.activeScene, { ...scene, title: event.target.value })}
                aria-label="场景名称"
                readOnly={props.readonly}
              />
              <em>{completedSceneRouteLabel(scene)}</em>
            </div>
          </div>

          <div className="draft-line-stack">
          {scene.lines.map((line, lineIndex) => {
            if (line.kind === "choice") {
              return (
                <div className="draft-branch-block choice" key={line.id}>
                  <div className="branch-marker" aria-hidden="true">△</div>
                  <div className="choice-editor-body">
                    <div className="choice-editor-head">
                      <strong>分支选项</strong>
                        <button
                          type="button"
                          disabled={props.readonly}
                          onClick={() => updateLine(lineIndex, { ...line, choices: [...(line.choices || []), { text: "新的选择", target: defaultChoiceTarget, target_scene_file: /\.txt$/i.test(defaultChoiceTarget) ? defaultChoiceTarget : undefined }] })}
                        >
                        添加选项
                      </button>
                    </div>
                    <div className="choice-option-list">
                      {(line.choices || []).map((choice, choiceIndex) => (
                        <div className="choice-option-row" key={`${line.id}-${choiceIndex}`}>
                          <input
                            value={choice.text}
                            onChange={(event) => updateChoice(lineIndex, choiceIndex, { ...choice, text: event.target.value })}
                            aria-label="选项文本"
                            readOnly={props.readonly}
                          />
                          <select
                            value={choiceTargetValue(choice)}
                            onChange={(event) => updateChoiceTarget(lineIndex, choiceIndex, choice, event.target.value)}
                            aria-label="跳转场景"
                            disabled={props.readonly}
                          >
                            {!targetOptions.some((option) => option.file === choiceTargetValue(choice)) && (
                              <option value={choiceTargetValue(choice)}>{choiceTargetValue(choice) || "未设置目标"}</option>
                            )}
                            {targetOptions.map((option) => (
                              <option key={option.file} value={option.file}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            disabled={props.readonly}
                            onClick={() => updateLine(lineIndex, { ...line, choices: (line.choices || []).filter((_, index) => index !== choiceIndex) })}
                          >
                            删除
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            }

            if (line.kind === "branch") {
              return (
                <div className="draft-branch-block branch" key={line.id}>
                  <div className="branch-marker" aria-hidden="true">△</div>
                  <div className="branch-label-body">
                    <span>分支内容</span>
                    <input
                      value={line.branchLabel || line.text}
                      onChange={(event) => updateLine(lineIndex, { ...line, text: event.target.value, branchLabel: event.target.value })}
                      aria-label="分支标识"
                      readOnly={props.readonly}
                    />
                  </div>
                  {!props.readonly && (
                    <button
                      type="button"
                      onClick={() => props.updateScene(props.activeScene, { ...scene, lines: scene.lines.filter((_, index) => index !== lineIndex) })}
                    >
                      删除
                    </button>
                  )}
                </div>
              );
            }

            const menuKey = `${props.activeScene}-${lineIndex}`;
            return (
              <div className={`draft-line ${line.kind} ${speakerMenu === menuKey ? "menu-open" : ""}`} key={line.id}>
                <div className="draft-speaker-wrap">
                  <button
                    className={`draft-speaker ${line.kind === "command" || props.readonly ? "static" : ""}`}
                    type="button"
                    disabled={props.readonly}
                    onClick={() => setSpeakerMenu(speakerMenu === menuKey ? null : menuKey)}
                  >
                    {line.kind === "narration" || line.kind === "command" ? "旁白" : line.speaker}
                  </button>
                  {speakerMenu === menuKey && (
                    <div className="speaker-popover">
                      {speakers.map((speaker) => (
                        <button key={speaker} type="button" onClick={() => switchSpeaker(lineIndex, speaker)}>
                          {speaker}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <textarea
                  value={line.text}
                  rows={draftLineRows(line.text)}
                  onChange={(event) => updateLine(lineIndex, { ...line, text: event.target.value })}
                  spellCheck={false}
                  aria-label="内容"
                  readOnly={props.readonly}
                />
                {!props.readonly && (
                  <button className="draft-line-delete" type="button" onClick={() => props.updateScene(props.activeScene, { ...scene, lines: scene.lines.filter((_, index) => index !== lineIndex) })}>
                    删除
                  </button>
                )}
              </div>
            );
          })}
          </div>
        </article>
      </div>
    </section>
  );
}
