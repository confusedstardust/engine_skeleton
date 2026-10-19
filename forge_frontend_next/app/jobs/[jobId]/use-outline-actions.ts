'use client';

import { forgeApi as api } from '../../../lib/api-client';

import type {
  StoryStep,
  NarrativeCharacter,
  NarrativeEnding,
  NarrativeNodeKind,
  GeneratedNarrativeNodeResponse,
  SyncNarrativeStructureResponse,
  SyncNarrativeStructureOptions,
  NarrativePlan,
} from '../../../domain/narrative';
import type { Job } from '../../../domain/jobs';

import { useCallback, useEffect } from 'react';

import { type WorkflowStage } from './workspace-workflow';

import type { RefObject, Dispatch, SetStateAction } from 'react';
type OutlineActionContext = {
  jobId: string;
  plan: NarrativePlan | null;
  planDirty: boolean;
  outlineLocked: boolean;
  planRef: RefObject<NarrativePlan | null>;
  setPlan: Dispatch<SetStateAction<NarrativePlan | null>>;
  setStage: (value: WorkflowStage) => void;
  refresh: (silent?: boolean) => Promise<void>;
  setPlanDirty: (value: boolean) => void;
  setBusy: (value: boolean) => void;
  setFlowSyncing: (value: boolean) => void;
  setOutlineSubmitted: (value: boolean) => void;
  setMessage: (value: string) => void;
  setErrorMessage: (value: string) => void;
  setPhaseBrief: (value: string) => void;
  setEndingBrief: (value: string) => void;
  setCharacterBrief: (value: string) => void;
  setPendingPhaseBrief: (value: string) => void;
  setPendingEndingBrief: (value: string) => void;
  setPendingCharacterBrief: (value: string) => void;
  phaseBrief: string;
  endingBrief: string;
  characterBrief: string;
};
export function useOutlineActions(context: OutlineActionContext) {
  const {
    jobId,
    plan,
    planDirty,
    outlineLocked,
    planRef,
    setPlan,
    setStage,
    refresh,
    setPlanDirty,
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
  } = context;
  function updatePlan(next: NarrativePlan) {
    setPlan(next);
    planRef.current = next;
    setPlanDirty(true);
  }

  const syncNarrativeStructure = useCallback(
    async (targetPlan?: NarrativePlan | null, options: SyncNarrativeStructureOptions = {}) => {
      const nextTarget = targetPlan || planRef.current;
      if (!nextTarget || (outlineLocked && !options.force)) return;
      const snapshot = JSON.stringify(nextTarget);
      if (options.quiet) {
        setFlowSyncing(true);
      } else {
        setBusy(true);
        setMessage('正在同步流程图...');
      }
      try {
        const result = await api<SyncNarrativeStructureResponse>(`/jobs/${jobId}/narrative-structure/sync`, {
          method: 'POST',
          body: JSON.stringify({ narrative_plan: nextTarget }),
        });
        const latestPlan = planRef.current;
        const canApply = !options.quiet || JSON.stringify(latestPlan) === snapshot;
        if (canApply) {
          setPlan(result.narrative_plan);
          planRef.current = result.narrative_plan;
          setPlanDirty(false);
        }
        if (!options.quiet) {
          setMessage(result.issues.length > 0 ? '流程图已同步，但仍有节点需要检查。' : '流程图已同步。');
          await refresh(true);
        }
      } catch (error) {
        if (!options.quiet) {
          setErrorMessage(error instanceof Error ? error.message : '同步流程图失败。');
        }
      } finally {
        if (options.quiet) {
          setFlowSyncing(false);
        } else {
          setBusy(false);
        }
      }
    },
    [
      jobId,
      outlineLocked,
      refresh,
      planRef,
      setBusy,
      setMessage,
      setFlowSyncing,
      setPlan,
      setPlanDirty,
      setErrorMessage,
    ],
  );

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
    setMessage('正在保存大纲并同步流程图...');
    try {
      const result = await api<SyncNarrativeStructureResponse>(`/jobs/${jobId}/narrative-structure/sync`, {
        method: 'POST',
        body: JSON.stringify({ narrative_plan: plan }),
      });
      setPlan(result.narrative_plan);
      planRef.current = result.narrative_plan;
      setPlanDirty(false);
      setMessage(result.issues.length > 0 ? '大纲已保存，流程图仍有节点需要检查。' : '大纲和流程图已保存。');
      await refresh(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '保存大纲失败。');
    } finally {
      setBusy(false);
    }
  }

  async function nextToScenes() {
    if (!plan) return;
    setBusy(true);
    setMessage('正在启动场景生成，将自动补全详细旁白和对话...');
    try {
      if (planDirty) {
        const result = await api<SyncNarrativeStructureResponse>(`/jobs/${jobId}/narrative-structure/sync`, {
          method: 'POST',
          body: JSON.stringify({ narrative_plan: plan }),
        });
        setPlan(result.narrative_plan);
        planRef.current = result.narrative_plan;
        setPlanDirty(false);
      }
      await api<Job>(`/jobs/${jobId}/phases/game_design`, {
        method: 'POST',
        body: JSON.stringify({ background: true }),
      });
      await refresh(true);
      setOutlineSubmitted(true);
      setStage('scenes');
      setMessage('场景正在连续生成，详细旁白和对话完成后即可审阅。');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '进入下一步失败。');
    } finally {
      setBusy(false);
    }
  }

  async function generateAndAppendNode(kind: NarrativeNodeKind, prompt: string) {
    if (!plan || outlineLocked) return;
    const brief = prompt.trim() || `新增${kind === 'phase' ? '阶段' : kind === 'ending' ? '结局' : '角色'}`;
    const nodeLabel = kind === 'phase' ? '阶段' : kind === 'ending' ? '结局' : '角色';
    setBusy(true);
    if (kind === 'phase') setPendingPhaseBrief(brief);
    if (kind === 'ending') setPendingEndingBrief(brief);
    if (kind === 'character') setPendingCharacterBrief(brief);
    try {
      let result: GeneratedNarrativeNodeResponse;
      try {
        result = await api<GeneratedNarrativeNodeResponse>(`/jobs/${jobId}/narrative-node`, {
          method: 'POST',
          body: JSON.stringify({ kind, prompt: brief, narrative_plan: plan }),
        });
      } catch (error) {
        throw new Error(`AI 生成${nodeLabel}失败：${error instanceof Error ? error.message : '未知错误'}`);
      }
      const nextPlan: NarrativePlan =
        result.kind === 'phase'
          ? { ...plan, story_progression: [...plan.story_progression, result.node as StoryStep] }
          : result.kind === 'ending'
          ? { ...plan, endings: [...plan.endings, result.node as NarrativeEnding] }
          : { ...plan, characters: [...plan.characters, result.node as NarrativeCharacter] };
      let synced: SyncNarrativeStructureResponse;
      try {
        synced = await api<SyncNarrativeStructureResponse>(`/jobs/${jobId}/narrative-structure/sync`, {
          method: 'POST',
          body: JSON.stringify({ narrative_plan: nextPlan }),
        });
      } catch (error) {
        // Preserve successful AI output locally so the user can retry without regenerating it.
        setPlan(nextPlan);
        planRef.current = nextPlan;
        setPlanDirty(true);
        throw new Error(
          `AI 已生成${nodeLabel}，但同步故事结构失败；新内容暂存在当前编辑器中，请点击“保存大纲”重试。${
            error instanceof Error ? ` 详情：${error.message}` : ''
          }`,
        );
      }
      setPlan(synced.narrative_plan);
      planRef.current = synced.narrative_plan;
      setPlanDirty(false);
      if (kind === 'phase') setPhaseBrief('');
      if (kind === 'ending') setEndingBrief('');
      if (kind === 'character') setCharacterBrief('');
      setMessage(
        `已使用 ${
          result.provider === 'mimo' ? 'MiMo' : result.provider === 'kimi' ? 'Kimi' : 'DeepSeek'
        } 新增${nodeLabel}并同步流程图。`,
      );
      await refresh(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '新增节点失败。');
    } finally {
      if (kind === 'phase') setPendingPhaseBrief('');
      if (kind === 'ending') setPendingEndingBrief('');
      if (kind === 'character') setPendingCharacterBrief('');
      setBusy(false);
    }
  }

  function addPhase() {
    void generateAndAppendNode('phase', phaseBrief);
  }

  function addEnding() {
    void generateAndAppendNode('ending', endingBrief);
  }

  function addCharacter() {
    void generateAndAppendNode('character', characterBrief);
  }

  return { updatePlan, syncNarrativeStructure, savePlan, nextToScenes, addPhase, addEnding, addCharacter };
}
