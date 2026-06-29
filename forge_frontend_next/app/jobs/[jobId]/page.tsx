"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { LaperAssetWorkbench } from "../../../components/laper-asset-workbench";
import { LaperInspectorShell } from "../../../components/laper-inspector-shell";
import { LaperOutlineWorkbench } from "../../../components/laper-outline-workbench";
import { LaperSceneWorkbench } from "../../../components/laper-scene-workbench";
import { withBasePath } from "../../base-path";
import {
  choiceTargetValue,
  compactId,
  completedSceneRouteLabel,
  draftLineRows,
  draftSceneRouteLabel,
  flowNodes,
  parseFlowEdges,
  parseGameDesignDraft,
  parsePlan,
  parseScenePlan,
  parseScenes,
  sceneMarkerLabel,
  sceneTargetOptions,
  serializeGameDesignJson
} from "./workspace-data";
import type {
  AssetReviewItem,
  AssetReviewResponse,
  GameDesignDraftScene,
  GeneratedNarrativeNodeResponse,
  Job,
  NarrativeCharacter,
  NarrativeEnding,
  NarrativeNodeKind,
  NarrativePlan,
  NodesResponse,
  SceneChoice,
  SceneDraft,
  SceneLine,
  ScenePlan,
  StoryStep,
  SyncNarrativeStructureOptions,
  SyncNarrativeStructureResponse
} from "./workspace-data";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withBasePath(`/api/forge${path}`), {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
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
  const autoMode = data?.job.options?.generation_mode === "auto";
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
  const outlineLocked = autoMode || outlineSubmitted || Boolean(designNode?.exists) || data?.job.phase === "GAME_DESIGN" || inAssetOrBuildStage;
  const scenesLocked = autoMode || inAssetOrBuildStage;
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

  useEffect(() => {
    if (!autoMode) return;
    if (canOpenAssets && stage !== "assets") setStage("assets");
    else if (!canOpenAssets && canOpenScenes && stage === "outline") setStage("scenes");
  }, [autoMode, canOpenAssets, canOpenScenes, stage]);

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
          {data.job.status === "DONE" && <a className="nav-login" href={withBasePath(`/play/${data.job.id}/`)} target="_blank">打开游戏</a>}
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
            autoMode={autoMode}
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
            readonly={autoMode}
            playUrl={withBasePath(`/play/${data.job.id}/`)}
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
            readonly={autoMode}
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
  readonly: boolean;
  playUrl: string;
}) {
  const assets = props.review?.assets || [];

  if (props.gameReady) {
    return (
      <section className="node-detail">
        <div className="node-placeholder done-placeholder">
          <strong>游戏生成完成。</strong>
          <span>素材和脚本已经写入游戏目录，现在可以直接打开试玩。</span>
          <a className="btn primary" href={props.playUrl} target="_blank">打开游戏</a>
        </div>
      </section>
    );
  }

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
    <LaperAssetWorkbench
      imageEnabled={props.review.image_enabled}
      assets={assets}
      busy={props.busy}
      readonly={props.readonly}
      activeAsset={props.activeAsset}
      assetPrompt={props.assetPrompt}
      setAssetPrompt={props.setAssetPrompt}
      openAsset={props.openAsset}
      closeAsset={props.closeAsset}
      regenerateAsset={props.regenerateAsset}
      buildGame={props.buildGame}
      displayName={assetDisplayName}
      sceneDisplayName={assetSceneDisplayName}
    />
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
  autoMode: boolean;
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
  if (!props.plan) {
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
    <LaperOutlineWorkbench
      plan={props.plan}
      busy={props.busy}
      planDirty={props.planDirty}
      flowSyncing={props.flowSyncing}
      locked={props.locked}
      autoMode={props.autoMode}
      phaseBrief={props.phaseBrief}
      endingBrief={props.endingBrief}
      characterBrief={props.characterBrief}
      pendingPhaseBrief={props.pendingPhaseBrief}
      pendingEndingBrief={props.pendingEndingBrief}
      pendingCharacterBrief={props.pendingCharacterBrief}
      setPhaseBrief={props.setPhaseBrief}
      setEndingBrief={props.setEndingBrief}
      setCharacterBrief={props.setCharacterBrief}
      updatePlan={props.updatePlan}
      addPhase={props.addPhase}
      addEnding={props.addEnding}
      addCharacter={props.addCharacter}
      savePlan={props.savePlan}
      syncStructure={props.syncStructure}
      nextToScenes={props.nextToScenes}
      renderFlowModal={(open, onClose) =>
        open ? (
          <div className="flow-modal-layer" role="dialog" aria-modal="true" aria-label="故事流程图">
            <button className="flow-modal-dismiss" type="button" aria-label="关闭流程图" onClick={onClose} />
            <section className="flow-modal">
              <div className="flow-modal-head">
                <div>
                  <span>{props.flowSyncing ? "同步中" : "自动同步"}</span>
                  <h3>故事流程图</h3>
                </div>
                <button className="btn outline" type="button" onClick={onClose}>关闭</button>
              </div>
              <div className="flow-modal-body">
                <NarrativeFlowPreview plan={props.plan} />
              </div>
            </section>
          </div>
        ) : null
      }
    />
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
  readonly: boolean;
  onChange: (scenes: GameDesignDraftScene[]) => void;
  saveDesignDraft: () => void;
  completeDesignDraft: () => void;
}) {
  const [activeDraftScene, setActiveDraftScene] = useState(0);
  const activeSceneIndex = Math.min(activeDraftScene, Math.max(props.scenes.length - 1, 0));
  const activeScene = props.scenes[activeSceneIndex];

  useEffect(() => {
    if (activeDraftScene > Math.max(props.scenes.length - 1, 0)) {
      setActiveDraftScene(Math.max(props.scenes.length - 1, 0));
    }
  }, [activeDraftScene, props.scenes.length]);

  if (!props.exists) {
    return (
      <section className="node-detail">
        <LoadingPlaceholder
          title="鍦烘櫙璁捐绋胯繕鍦ㄧ敓鎴愩€?
          brief="鐢熸垚瀹屾垚鍚庯紝杩欓噷浼氭寜鍦烘櫙鍗＄墖灞曠ず锛岀‘璁ゅ悗鍐嶇敓鎴愯缁嗘梺鐧藉拰瀵硅瘽銆?
        />
      </section>
    );
  }

  if (!activeScene) {
    return (
      <section className="node-detail">
        <div className="node-placeholder">
          <strong>鍦烘櫙璁捐绋胯繕娌℃湁鍙睍绀虹殑鍦烘櫙銆?/strong>
          <span>璇风◢鍚庡埛鏂帮紝鎴栧洖鍒板ぇ绾查噸鏂扮敓鎴愬満鏅璁＄銆?/span>
        </div>
      </section>
    );
  }

  return (
    <LaperSceneWorkbench
      mode="draft"
      title={props.plan?.title || "鍦烘櫙璁捐绋?}
      subtitle="鍏堟寜闃舵鍜岀粨灞€瀹￠槄鍦烘櫙缁撴瀯锛岀‘璁ゅ悗鍐嶇敓鎴愯缁嗘梺鐧戒笌瀵硅瘽銆?
      plan={props.plan}
      scenes={props.scenes}
      activeScene={activeDraftScene}
      setActiveScene={setActiveDraftScene}
      onScenesChange={(scenes) => props.onChange(scenes as GameDesignDraftScene[])}
      readonly={props.readonly}
      busy={props.busy}
      routeLabel={(scene) => draftSceneRouteLabel(scene as GameDesignDraftScene, props.plan)}
      markerLabel={(scene) => (scene.marker === "Ending" ? "缁撳眬" : "鍦烘櫙")}
      inspector={
        <LaperInspectorShell
          eyebrow="淇℃伅"
          title="璁捐绋挎瑙?
          stats={[
            { label: "鍦烘", value: props.scenes.length },
            { label: "缁撳眬", value: props.scenes.filter((s) => s.marker === "Ending").length },
            { label: "鎬昏鏁?, value: props.scenes.reduce((n, s) => n + s.lines.length, 0) }
          ]}
          note="纭鍦烘櫙缁撴瀯涓庡鐧藉畨鎺掑悗锛屽啀鐢熸垚璇︾粏鏃佺櫧涓庡璇濄€?
          footer={
            !props.readonly ? (
              <>
                <button className="btn outline" type="button" disabled={props.busy || !props.dirty} onClick={props.saveDesignDraft}>
                  淇濆瓨璁捐绋?
                </button>
                <button className="btn primary" type="button" disabled={props.busy || props.scenes.length === 0} onClick={props.completeDesignDraft}>
                  纭骞剁敓鎴愯缁嗗満鏅?
                </button>
              </>
            ) : undefined
          }
        />
      }
    />
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
  const targetOptions = useMemo(
    () => sceneTargetOptions(props.scenePlan, props.plan, props.scenes, scene?.header),
    [props.scenePlan, props.plan, props.scenes, scene?.header]
  );

  if (!scene) {
    return (
      <section className="node-detail">
        <LoadingPlaceholder
          title="璇︾粏鍦烘櫙杩樺湪鐢熸垚銆?
          brief="鐢熸垚瀹屾垚鍚庯紝杩欓噷浼氭寜鍦烘櫙灞曠ず鏃佺櫧銆佸鐧藉拰鍒嗘敮鍐呭銆?
        />
      </section>
    );
  }

  return (
    <LaperSceneWorkbench
      mode="complete"
      title={props.plan?.title || "璇︾粏鍦烘櫙"}
      subtitle="鎸夊満鏅闃呮梺鐧姐€佸鐧藉拰鍒嗘敮鍐呭銆?
      plan={props.plan}
      scenes={props.scenes}
      activeScene={props.activeScene}
      setActiveScene={props.setActiveScene}
      onScenesChange={(nextScenes) => {
        props.setScenes(nextScenes as SceneDraft[]);
        props.setScenesDirty(true);
      }}
      readonly={props.readonly}
      busy={props.busy}
      routeLabel={(item) => completedSceneRouteLabel(item as SceneDraft)}
      markerLabel={(item) => sceneMarkerLabel(item as SceneDraft)}
      targetOptions={targetOptions}
      inspector={
        <LaperInspectorShell
          eyebrow="淇℃伅"
          title="鍦烘櫙姒傝"
          stats={[
            { label: "鍦烘", value: props.scenes.length },
            { label: "褰撳墠琛屾暟", value: scene.lines.length },
            { label: "鐘舵€?, value: props.scenesDirty ? "鏈繚瀛? : "宸插悓姝? }
          ]}
          note="鎸夊満鏅闃呮梺鐧姐€佸鐧藉拰鍒嗘敮鍐呭锛屼繚瀛樺悗杩涘叆绱犳潗闃舵銆?
          footer={
            !props.readonly ? (
              <button className="btn primary" type="button" disabled={props.busy} onClick={props.saveScenes}>
                淇濆瓨骞剁敓鎴愮礌鏉?
              </button>
            ) : undefined
          }
        />
      }
    />
  );
}
