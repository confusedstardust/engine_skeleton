'use client';
import { useToast } from '../../../components/ui/toast';
import { useRouter } from 'next/navigation';
import { useOutlineActions } from './use-outline-actions';
import {
  parseSceneConnectionReport,
  parsePlan,
  parseScenePlan,
  serializeGameDesignJson,
  parseScenes,
} from './workspace-data';
import { forgeApi as api } from '../../../lib/api-client';

import type { StagedScenePresentation } from '../../../domain/assets';
import type { NarrativePlan, SceneDraft } from '../../../domain/narrative';
import type { Job } from '../../../domain/jobs';

import { useConfirmation } from '../../../components/ui/modal';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { repairContinuationLabels, validateSceneConnections } from '../../../components/scene-connections';

import { useJobResources } from '../../../hooks/use-job-resources';
import { createJobAssetActions } from './job-asset-actions';
import { failedPhaseRetry, type WorkflowStage } from './workspace-workflow';

export function useJobWorkspace(jobId: string) {
  const notify = useToast();
  const confirm = useConfirmation();
  const router = useRouter();
  const [message, setMessageValue] = useState('正在读取任务...');
  const [operationError, setOperationError] = useState(false);
  const setMessage = useCallback((value: string) => {
    setMessageValue(value);
    setOperationError(false);
  }, []);
  const setErrorMessage = useCallback((value: string) => {
    setMessageValue(value);
    setOperationError(true);
  }, []);
  const { data, setData, assetReview, refresh } = useJobResources(jobId, setMessage, setErrorMessage);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<WorkflowStage>('outline');
  const [editScope, setEditScope] = useState<'none' | 'draft'>('none');
  const [stageHydrated, setStageHydrated] = useState(false);
  const [plan, setPlan] = useState<NarrativePlan | null>(null);
  const [planDirty, setPlanDirty] = useState(false);
  const [flowSyncing, setFlowSyncing] = useState(false);
  const [phaseBrief, setPhaseBrief] = useState('');
  const [endingBrief, setEndingBrief] = useState('');
  const [characterBrief, setCharacterBrief] = useState('');
  const [pendingPhaseBrief, setPendingPhaseBrief] = useState('');
  const [pendingEndingBrief, setPendingEndingBrief] = useState('');
  const [pendingCharacterBrief, setPendingCharacterBrief] = useState('');
  const [outlineSubmitted, setOutlineSubmitted] = useState(false);
  const [scenes, setScenes] = useState<SceneDraft[]>([]);
  const [activeScene, setActiveScene] = useState(0);
  const [scenesDirty, setScenesDirty] = useState(false);
  const [connectionCheckAttempted, setConnectionCheckAttempted] = useState(false);
  const connectionErrors = useMemo(
    () => (connectionCheckAttempted ? validateSceneConnections(scenes) : {}),
    [scenes, connectionCheckAttempted],
  );
  const [activeAssetFilename, setActiveAssetFilename] = useState<string | null>(null);
  const [assetPrompt, setAssetPrompt] = useState('');
  const [assetPromptDirty, setAssetPromptDirty] = useState(false);
  const [voiceGeneratingSpeaker, setVoiceGeneratingSpeaker] = useState<string | null>(null);
  const planRef = useRef<NarrativePlan | null>(null);
  const publishedSeenRef = useRef(false);

  const narrativeNode = data?.nodes.find((node) => node.key === 'narrative_plan');
  const rawDesignNode = data?.nodes.find((node) => node.key === 'game_design');
  const scenePlanNode = data?.nodes.find((node) => node.key === 'scene_plan');
  const designNode = data?.nodes.find((node) => node.key === 'game_design_completed');
  const assetManifestNode = data?.nodes.find((node) => node.key === 'asset_manifest');
  const sceneConnectionNode = data?.nodes.find((node) => node.key === 'scene_connection_report');
  const sceneConnectionReport = useMemo(
    () => parseSceneConnectionReport(sceneConnectionNode?.content || null),
    [sceneConnectionNode?.content],
  );
  const scenePlanContent = scenePlanNode?.content || null;
  const scenePlan = useMemo(() => parseScenePlan(scenePlanContent), [scenePlanContent]);
  const isGenerating = data?.job.status === 'RUNNING' || data?.job.status === 'QUEUED';
  const failedRetry = data ? failedPhaseRetry(data.job) : null;
  const activePhase = data?.job.phase || '';
  const isDesignCompletionRunning = isGenerating && activePhase === 'GAME_DESIGN_COMPLETION';
  const assetGenerationPhases = new Set([
    'ASSET_REVIEW',
    'ASSET_PLANNING',
    'ASSET_GENERATION',
    'TTS_PREVIEW_GENERATION',
  ]);
  const isAssetGenerationRunning = isGenerating && assetGenerationPhases.has(activePhase);
  const gameBuildPhases = new Set([
    'GAME_BUILD',
    'SCRIPT_REWRITE',
    'SOUND_EFFECT_PLANNING',
    'TTS_GENERATION',
    'SCENE_WRITING',
    'SCENE_CONNECTION_CHECK',
    'VALIDATING',
  ]);
  const isGameBuildRunning = isGenerating && gameBuildPhases.has(activePhase);
  const autoMode = data?.job.options?.generation_mode === 'auto';
  const hasPublishedBuild = Boolean(data?.job.has_published_build ?? data?.job.status === 'DONE');
  const assetPhases = new Set([
    'ASSET_REVIEW',
    'ASSET_PLANNING',
    'ASSET_GENERATION',
    'TTS_PREVIEW_GENERATION',
    'GAME_BUILD',
    'SCRIPT_REWRITE',
    'SOUND_EFFECT_PLANNING',
    'TTS_GENERATION',
    'SCENE_WRITING',
    'SCENE_CONNECTION_CHECK',
    'VALIDATING',
  ]);
  const inAssetOrBuildStage =
    Boolean(assetManifestNode?.exists) ||
    Boolean(assetReview?.assets.length) ||
    assetPhases.has(activePhase) ||
    hasPublishedBuild;
  const outlineLocked =
    autoMode ||
    outlineSubmitted ||
    Boolean(designNode?.exists) ||
    activePhase === 'GAME_DESIGN' ||
    activePhase === 'GAME_DESIGN_DRAFT' ||
    activePhase === 'GAME_DESIGN_COMPLETION' ||
    inAssetOrBuildStage;
  const scenesLocked = isGenerating || (hasPublishedBuild ? editScope === 'none' : autoMode || inAssetOrBuildStage);
  const assetsLocked = isGenerating || (hasPublishedBuild ? editScope === 'none' : autoMode);
  const canOpenScenes = outlineLocked || Boolean(rawDesignNode?.exists) || Boolean(designNode?.exists);
  const canOpenAssets = inAssetOrBuildStage;
  const activeAsset = assetReview?.assets.find((asset) => asset.filename === activeAssetFilename) || null;

  const observedNarrativeContent = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    // Saving changes dirty state, but must never rehydrate an unchanged cache.
    if (observedNarrativeContent.current === narrativeNode?.content) return;
    observedNarrativeContent.current = narrativeNode?.content;
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
      const repaired = repairContinuationLabels(parsed);
      setScenes(repaired);
      if (repaired.some((scene, index) => scene !== parsed[index])) setScenesDirty(true);
      setActiveScene(0);
    }
  }, [designNode?.content, scenesDirty, plan, rawDesignNode?.content, scenePlan]);

  useEffect(() => {
    if (!data || stageHydrated) return;
    if (hasPublishedBuild) setStage('complete');
    else if (canOpenAssets) setStage('assets');
    else if (canOpenScenes) setStage('scenes');
    setStageHydrated(true);
  }, [canOpenAssets, canOpenScenes, data, hasPublishedBuild, stageHydrated]);

  useEffect(() => {
    if (!autoMode || hasPublishedBuild) return;
    if (canOpenAssets && stage !== 'assets') setStage('assets');
    else if (!canOpenAssets && canOpenScenes && stage === 'outline') setStage('scenes');
  }, [autoMode, canOpenAssets, canOpenScenes, hasPublishedBuild, stage]);

  useEffect(() => {
    if (hasPublishedBuild && !publishedSeenRef.current) {
      publishedSeenRef.current = true;
      const directEdit = new URLSearchParams(window.location.search).get('edit') === '1' && !isGenerating && data?.job.build_state !== 'BUILDING';
      setEditScope(directEdit ? 'draft' : 'none');
      setStage(directEdit ? 'assets' : 'complete');
    }
  }, [hasPublishedBuild, isGenerating, data?.job.build_state]);

  useEffect(() => {
    if (!planDirty && !scenesDirty && !assetPromptDirty) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => window.removeEventListener('beforeunload', warnBeforeUnload);
  }, [assetPromptDirty, planDirty, scenesDirty]);

  function beginCompletedEdit() {
    setEditScope('draft');
    setStage('assets');
    setMessage(
      '已进入草稿编辑；可在素材审阅页调整素材、音乐、语音和特效，也可切换到场景页修改内容。当前可玩版本不会立即改变。',
    );
  }

  async function exitCompletedEdit() {
    if ((planDirty || scenesDirty || assetPromptDirty) && !(await confirm('还有未保存的修改，确定退出编辑吗？')))
      return;
    setScenesDirty(false);
    setAssetPromptDirty(false);
    setPlanDirty(false);
    setEditScope('none');
    router.push('/history');
  }

  const { updatePlan, syncNarrativeStructure, savePlan, nextToScenes, addPhase, addEnding, addCharacter } =
    useOutlineActions({
      jobId,
      plan,
      planDirty,
      outlineLocked,
      planRef,
      setData,
      setPlan,
      setStage,
      refresh,
      setPlanDirty,
      notify,
      setBusy,
      setFlowSyncing,
      setOutlineSubmitted,
      setMessage,
      setErrorMessage,
      setPhaseBrief,
      setEndingBrief,
      setCharacterBrief,
      setPendingPhaseBrief,
      setPendingEndingBrief,
      setPendingCharacterBrief,
      phaseBrief,
      endingBrief,
      characterBrief,
    });

  function checkAllSceneConnections() {
    setConnectionCheckAttempted(true);
    const errors = validateSceneConnections(scenes);
    const first = scenes.findIndex((scene) => !!errors[scene.header]);
    if (first < 0 && scenes.length) return true;
    if (first >= 0) setActiveScene(first);
    setStage('scenes');
    setMessage(
      scenes.length
        ? `场景衔接检查未通过：${Object.keys(errors).length} 个场景需要修正。请查看红色标记和场景末尾的错误提示。`
        : '场景内容尚未加载完成，请稍后重试。',
    );
    return false;
  }

  async function saveScenes(applyChanges = false) {
    if ((!hasPublishedBuild || applyChanges) && !checkAllSceneConnections()) return;
    setBusy(true);
    setMessage(
      scenesDirty ? '正在保存场景内容...' : hasPublishedBuild ? '正在应用已保存的修改...' : '正在启动素材阶段...',
    );
    try {
      if (scenesDirty) {
        await api(`/jobs/${jobId}/artifacts`, {
          method: 'PATCH',
          body: JSON.stringify({
            path: 'state/game_design_completed.json',
            content: serializeGameDesignJson(scenes),
            base_revision: data?.job.draft_revision ?? 0,
          }),
        });
        setScenesDirty(false);
      }
      if (hasPublishedBuild) {
        if (applyChanges) {
          await api<Job>(`/jobs/${jobId}/apply-draft`, {
            method: 'POST',
            body: JSON.stringify({ background: true }),
          });
          setEditScope('none');
          setStage('complete');
          setMessage('正在把已保存的场景修改应用到当前游戏；未修改内容会保持原样。');
          notify('场景修改已提交，正在应用到游戏。', 'success');
        } else {
          setMessage('场景草稿已保存；当前游戏仍是上一次发布版本。');
          notify('场景草稿已保存；当前游戏仍是上一次发布版本。', 'success');
        }
        await refresh(true);
        return;
      }
      await api<Job>(`/jobs/${jobId}/phases/asset_review`, {
        method: 'POST',
        body: JSON.stringify({ background: true }),
      });
      setStage('assets');
      setMessage('素材规划和生成已启动，完成后可以审阅角色卡和场景卡。');
      notify('素材规划和生成已启动。', 'success');
      await refresh(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '启动素材阶段失败。');
    } finally {
      setBusy(false);
    }
  }

  const {
    regenerateAsset,
    previewSceneMusic,
    uploadAsset,
    loadLibraryAssets,
    useLibraryAsset,
    removeAssetBackground,
    previewCharacterVoice,
  } = createJobAssetActions({
    notify,
    jobId,
    data,
    setBusy,
    setMessage,
    setErrorMessage,
    refresh,
    setAssetPromptDirty,
    setVoiceGeneratingSpeaker,
  });

  async function saveStagedPresentation(staged: StagedScenePresentation | undefined, revision: number) {
    if (staged) {
      for (const [filename, crop] of Object.entries(staged.avatarCrops)) {
        const saved = await api<{ job: Job }>(`/jobs/${jobId}/assets/avatar-crop`, {
          method: 'POST',
          body: JSON.stringify({
            filename,
            zoom: crop.zoom,
            offset_x: crop.offsetX,
            offset_y: crop.offsetY,
            base_revision: revision,
          }),
        });
        revision = saved.job.draft_revision ?? revision;
        setData((previous) => (previous ? { ...previous, job: saved.job } : previous));
      }
    }
    if (staged && (Object.keys(staged.music).length || Object.keys(staged.effects).length)) {
      const saved = await api<{ job: Job }>(`/jobs/${jobId}/scene-presentation-draft`, {
        method: 'PUT',
        body: JSON.stringify({ music: staged.music, effects: staged.effects, base_revision: revision }),
      });
      revision = saved.job.draft_revision ?? revision;
      setData((previous) => (previous ? { ...previous, job: saved.job } : previous));
    }
    return revision;
  }

  async function buildGameFromAssets(staged?: StagedScenePresentation) {
    if (!checkAllSceneConnections()) return false;
    setBusy(true);
    setMessage(
      staged
        ? '正在统一保存素材调整并应用到游戏...'
        : hasPublishedBuild
        ? '正在应用草稿中的局部修改...'
        : '正在改写 WebGAL 脚本并生成游戏...',
    );
    try {
      let revision = data?.job.draft_revision ?? 0;
      if (scenesDirty) {
        const saved = await api<{ job: Job }>(`/jobs/${jobId}/artifacts`, {
          method: 'PATCH',
          body: JSON.stringify({
            path: 'state/game_design_completed.json',
            content: serializeGameDesignJson(scenes),
            base_revision: revision,
          }),
        });
        revision = saved.job.draft_revision ?? revision;
        setScenesDirty(false);
        setData((previous) => (previous ? { ...previous, job: saved.job } : previous));
      }
      revision = await saveStagedPresentation(staged, revision);
      await api<Job>(hasPublishedBuild ? `/jobs/${jobId}/apply-draft` : `/jobs/${jobId}/phases/game_build`, {
        method: 'POST',
        body: JSON.stringify({ background: true }),
      });
      if (hasPublishedBuild) {
        setEditScope('none');
        setStage('complete');
      }
      setMessage(
        hasPublishedBuild
          ? '修改同步已启动；未修改的场景和素材会保持原样。'
          : '游戏生成已启动，完成后可以点击右上角打开游戏。',
      );
      await refresh(true);
      return true;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '生成游戏失败。');
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function continueSceneGeneration() {
    setBusy(true);
    setMessage('正在继续生成详细旁白和对话...');
    try {
      await api<Job>(`/jobs/${jobId}/phases/game_design_completion`, {
        method: 'POST',
        body: JSON.stringify({ background: true }),
      });
      await refresh(true);
      setMessage('详细场景正在生成，完成后即可审阅。');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '继续生成详细场景失败。');
    } finally {
      setBusy(false);
    }
  }

  async function retryFailedPhase() {
    return retryPhase();
  }

  async function retryPhase(staged?: StagedScenePresentation) {
    if (!failedRetry) return false;
    setBusy(true);
    setStage(failedRetry.stage);
    setMessage(failedRetry.pendingMessage);
    try {
      await saveStagedPresentation(staged, data?.job.draft_revision ?? 0);
      await api<Job>(`/jobs/${jobId}/${failedRetry.path}`, {
        method: 'POST',
        body: JSON.stringify({ background: true }),
      });
      await refresh(true);
      setMessage(failedRetry.successMessage);
      return true;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '重试失败，请稍后再试。');
      return false;
    } finally {
      setBusy(false);
    }
  }

  function updateScene(index: number, next: SceneDraft) {
    setScenes((current) => current.map((scene, sceneIndex) => (sceneIndex === index ? next : scene)));
    setScenesDirty(true);
  }

  return {
    confirm,
    data,
    message,
    operationError,
    assetReview,
    busy,
    stage,
    setStage,
    editScope,
    plan,
    planDirty,
    flowSyncing,
    phaseBrief,
    setPhaseBrief,
    endingBrief,
    setEndingBrief,
    characterBrief,
    setCharacterBrief,
    pendingPhaseBrief,
    pendingEndingBrief,
    pendingCharacterBrief,
    scenes,
    setScenes,
    activeScene,
    setActiveScene,
    scenesDirty,
    setScenesDirty,
    connectionErrors,
    setActiveAssetFilename,
    assetPrompt,
    setAssetPrompt,
    assetPromptDirty,
    setAssetPromptDirty,
    voiceGeneratingSpeaker,
    rawDesignNode,
    designNode,
    sceneConnectionReport,
    scenePlan,
    isGenerating,
    failedRetry,
    isDesignCompletionRunning,
    isAssetGenerationRunning,
    isGameBuildRunning,
    autoMode,
    hasPublishedBuild,
    outlineLocked,
    scenesLocked,
    assetsLocked,
    canOpenScenes,
    canOpenAssets,
    activeAsset,
    beginCompletedEdit,
    exitCompletedEdit,
    updatePlan,
    syncNarrativeStructure,
    savePlan,
    nextToScenes,
    addPhase,
    addEnding,
    addCharacter,
    saveScenes,
    regenerateAsset,
    previewSceneMusic,
    uploadAsset,
    loadLibraryAssets,
    useLibraryAsset,
    removeAssetBackground,
    previewCharacterVoice,
    buildGameFromAssets,
    continueSceneGeneration,
    retryFailedPhase,
    retryPhase,
    updateScene,
  };
}
