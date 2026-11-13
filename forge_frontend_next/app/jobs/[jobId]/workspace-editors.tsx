'use client';
import { Button } from '../../../components/ui/button';
import { completedSceneRouteLabel, sceneMarkerLabel, sceneTargetOptions } from './workspace-data';

import type {
  SyncNarrativeStructureOptions,
  NarrativePlan,
  ScenePlan,
  SceneDraft,
} from '../../../domain/narrative';

import { ContentDialog } from '../../../components/ui/content-dialog';
import { useMemo } from 'react';
import { StoryFlowView } from '../../../components/story-flow-view';
import { planningGraph } from '../../../components/story-graph-data';

import { LaperInspectorShell } from '../../../components/laper-inspector-shell';
import { LaperOutlineWorkbench } from '../../../components/laper-outline-workbench';
import { LaperSceneWorkbench } from '../../../components/laper-scene-workbench';

import { LoadingPlaceholder, FailedPlaceholder } from './workspace-placeholders';

export function OutlineEditor(props: {
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
  retryAction?: () => void;
  retryLabel?: string;
}) {
  if (!props.plan) {
    return (
      <section className="node-detail">
        {props.retryAction ? (
          <FailedPlaceholder
            title="故事大纲生成失败。"
            brief="后台自动重试仍未成功，你可以保留当前任务并重新生成这一阶段。"
            action={props.retryAction}
            actionLabel={props.retryLabel || '重试生成故事大纲'}
            busy={props.busy}
          />
        ) : (
          <LoadingPlaceholder title="故事大纲还没有生成完成。" brief="页面会自动刷新，大纲出现后就可以开始审阅。" />
        )}
      </section>
    );
  }

  const plan = props.plan;

  return (
    <LaperOutlineWorkbench
      plan={plan}
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
      retryAction={props.retryAction}
      retryLabel={props.retryLabel}
      renderFlowModal={(open, onClose) =>
        open ? (
          <ContentDialog title="故事流程图" subtitle={props.flowSyncing ? '同步中' : '自动同步'} onClose={onClose} layerClassName="flow-modal-layer" className="flow-modal" headerClassName="flow-modal-head" bodyClassName="flow-modal-body">
            <NarrativeFlowPreview plan={plan} syncStructure={props.syncStructure} />
          </ContentDialog>
        ) : null
      }
    />
  );
}

export function NarrativeFlowPreview(props: {
  plan: NarrativePlan;
  syncStructure: (targetPlan?: NarrativePlan | null, options?: SyncNarrativeStructureOptions) => Promise<void>;
}) {
  const graph = useMemo(() => planningGraph(props.plan), [props.plan]);
  return <StoryFlowView graph={graph} />;
}

export function SceneGenerationStatus(props: {
  busy: boolean;
  generatingCompletion: boolean;
  resumeAction?: () => void;
  retryAction?: () => void;
  retryLabel?: string;
}) {
  return (
    <section className="node-detail">
      {props.retryAction ? (
        <FailedPlaceholder
          title="场景生成失败。"
          brief="可以从失败阶段重试；详细场景完成后再统一审阅。"
          action={props.retryAction}
          actionLabel={props.retryLabel || '重试生成场景'}
          busy={props.busy}
        />
      ) : props.resumeAction ? (
        <div className="node-placeholder">
          <strong>详细场景尚未生成。</strong>
          <span>此任务已保存场景设计稿，可以继续生成详细旁白和对话，无需再次确认设计稿。</span>
          <Button variant="primary" type="button" busy={Boolean(props.busy)} onClick={props.resumeAction}>
            继续生成详细场景
          </Button>
        </div>
      ) : (
        <LoadingPlaceholder
          title={props.generatingCompletion ? '详细场景正在生成。' : '场景正在生成。'}
          brief="系统会连续生成场景设计和详细旁白、对话，完成后自动进入逐场景审阅。"
        />
      )}
    </section>
  );
}

export function SceneEditor(props: {
  connectionErrors: Record<string, string>;
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
  saveScenes: (rebuild?: boolean) => void;
  published: boolean;
}) {
  const scene = props.scenes[props.activeScene];
  const targetOptions = useMemo(
    () => sceneTargetOptions(props.scenePlan, props.plan, props.scenes, scene?.header),
    [props.scenePlan, props.plan, props.scenes, scene?.header],
  );

  if (!scene) {
    return (
      <section className="node-detail">
        <LoadingPlaceholder title="详细场景还在生成。" brief="生成完成后，这里会按场景展示旁白、对白和分支内容。" />
      </section>
    );
  }

  return (
    <LaperSceneWorkbench
      mode="complete"
      connectionErrors={props.connectionErrors}
      title={props.plan?.title || '详细场景'}
      subtitle="按场景审阅旁白、对白和分支内容。"
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
          eyebrow="信息"
          title="场景概览"
          stats={[
            { label: '场次', value: props.scenes.length },
            { label: '当前行数', value: scene.lines.length },
            { label: '状态', value: props.scenesDirty ? '未保存' : '已同步' },
          ]}
          note={
            props.published
              ? '修改会先保存为草稿；应用时只更新发生变化的场景。'
              : '按场景审阅旁白、对白和分支内容，保存后进入素材阶段。'
          }
          footer={
            !props.readonly ? (
              props.published ? (
                <>
                  <Button
                    variant="outline"
                    type="button"
                    busy={Boolean(props.busy)} disabled={props.busy || !props.scenesDirty}
                    onClick={() => props.saveScenes(false)}
                  >
                    仅保存草稿
                  </Button>
                  <Button
                    variant="primary"
                    type="button"
                    busy={Boolean(props.busy)}
                    onClick={() => props.saveScenes(true)}
                  >
                    保存并应用到游戏
                  </Button>
                </>
              ) : (
                <Button
                  variant="primary"
                  type="button"
                  busy={Boolean(props.busy)}
                  onClick={() => props.saveScenes(false)}
                >
                  保存并生成素材
                </Button>
              )
            ) : undefined
          }
        />
      }
    />
  );
}
