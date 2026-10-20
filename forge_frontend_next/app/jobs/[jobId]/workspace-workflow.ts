import type { Job } from '../../../domain/jobs';
export type WorkflowStage = 'outline' | 'scenes' | 'assets' | 'complete';

export type FailedPhaseRetry = {
  path: string;
  label: string;
  pendingMessage: string;
  successMessage: string;
  stage: WorkflowStage;
};

export function failedPhaseRetry(job: Job): FailedPhaseRetry | null {
  if (job.status !== 'FAILED') return null;

  const phase = job.phase || '';
  const stage: WorkflowStage =
    phase === 'NARRATIVE_PLANNING'
      ? 'outline'
      : ['GAME_DESIGN', 'GAME_DESIGN_DRAFT', 'GAME_DESIGN_COMPLETION'].includes(phase)
      ? 'scenes'
      : 'assets';

  if (job.options?.generation_mode === 'auto') {
    return {
      path: 'run',
      label: '重试自动生成',
      pendingMessage: '正在重新启动自动生成流程...',
      successMessage: '自动生成已重新启动，页面会持续更新进度。',
      stage,
    };
  }

  if (phase === 'NARRATIVE_PLANNING') {
    return {
      path: 'phases/narrative',
      label: '重试生成故事大纲',
      pendingMessage: '正在重试故事大纲生成...',
      successMessage: '故事大纲已重新加入生成队列。',
      stage,
    };
  }
  if (phase === 'GAME_DESIGN' || phase === 'GAME_DESIGN_DRAFT') {
    return {
      path: 'phases/game_design',
      label: '重试生成场景',
      pendingMessage: '正在重新生成场景及详细旁白和对话...',
      successMessage: '场景已重新加入生成队列，将自动继续生成详细场景。',
      stage,
    };
  }
  if (phase === 'GAME_DESIGN_COMPLETION') {
    return {
      path: 'phases/game_design_completion',
      label: '重试生成详细场景',
      pendingMessage: '正在重试详细场景生成...',
      successMessage: '详细场景已重新加入生成队列。',
      stage,
    };
  }
  if (['ASSET_REVIEW', 'ASSET_PLANNING', 'ASSET_GENERATION', 'TTS_PREVIEW_GENERATION'].includes(phase)) {
    return {
      path: 'phases/asset_review',
      label: '重试生成素材',
      pendingMessage: '正在重试素材规划与生成...',
      successMessage: '素材阶段已重新加入生成队列。',
      stage,
    };
  }
  if (
    [
      'GAME_BUILD',
      'SCRIPT_REWRITE',
      'SOUND_EFFECT_PLANNING',
      'TTS_GENERATION',
      'SCENE_WRITING',
      'SCENE_CONNECTION_CHECK',
      'VALIDATING',
    ].includes(phase)
  ) {
    return {
      path: 'phases/game_build',
      label: '重试生成游戏',
      pendingMessage: '正在从游戏构建阶段重新生成...',
      successMessage: '游戏构建已重新加入生成队列。',
      stage,
    };
  }
  return null;
}
