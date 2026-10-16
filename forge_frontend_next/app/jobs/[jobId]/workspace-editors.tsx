'use client';
import { draftSceneRouteLabel, completedSceneRouteLabel, sceneMarkerLabel, sceneTargetOptions } from './workspace-data';

import type {
  SyncNarrativeStructureOptions,
  NarrativePlan,
  ScenePlan,
  SceneDraft,
  GameDesignDraftScene,
} from '../../../domain/narrative';

import { ModalBody, ModalFrame } from '../../../components/ui/modal';
import { useEffect, useMemo, useState } from 'react';
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
          <ModalFrame title="故事流程图" onClose={onClose}>
            <div className="flow-modal-layer">
              <button className="flow-modal-dismiss" type="button" aria-label="关闭流程图" onClick={onClose} />
              <ModalBody><section className="flow-modal">
                <div className="flow-modal-head">
                  <div>
                    <span>{props.flowSyncing ? '同步中' : '自动同步'}</span>
                    <h3>故事流程图</h3>
                  </div>
                  <button className="btn outline" type="button" onClick={onClose}>
                    关闭
                  </button>
                </div>
                <div className="flow-modal-body">
                  <NarrativeFlowPreview plan={plan} syncStructure={props.syncStructure} />
                </div>
              </section></ModalBody>
            </div>
          </ModalFrame>
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

export function DesignDraftEditor(props: {
  plan: NarrativePlan | null;
  scenes: GameDesignDraftScene[];
  exists: boolean;
  busy: boolean;
  dirty: boolean;
  readonly: boolean;
  generatingDraft: boolean;
  generatingCompletion: boolean;
  onChange: (scenes: GameDesignDraftScene[]) => void;
  saveDesignDraft: () => void;
  completeDesignDraft: () => void;
  retryAction?: () => void;
  retryLabel?: string;
}) {
  const [activeDraftScene, setActiveDraftScene] = useState(0);
  const activeSceneIndex = Math.min(activeDraftScene, Math.max(props.scenes.length - 1, 0));
  const activeScene = props.scenes[activeSceneIndex];

  useEffect(() => {
    if (activeDraftScene > Math.max(props.scenes.length - 1, 0)) {
      setActiveDraftScene(Math.max(props.scenes.length - 1, 0));
    }
  }, [activeDraftScene, props.scenes.length]);

  if (props.generatingDraft || !props.exists) {
    return (
      <section className="node-detail">
        {props.retryAction ? (
          <FailedPlaceholder
            title="场景设计稿生成失败。"
            brief="自动重试仍未完成场景设计稿，可以直接重新执行这一阶段。"
            action={props.retryAction}
            actionLabel={props.retryLabel || '重试生成场景设计稿'}
            busy={props.busy}
          />
        ) : (
          <LoadingPlaceholder
            title="场景设计稿还在生成。"
            brief="生成完成后，这里会按场景卡片展示，确认后再生成详细旁白和对话。"
          />
        )}
      </section>
    );
  }

  if (props.generatingCompletion) {
    return (
      <section className="node-detail">
        <LoadingPlaceholder
          title="详细场景正在生成。"
          brief="系统正在根据场景设计稿补全旁白、对话和分支内容，完成后会自动进入逐场景审阅。"
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
    <LaperSceneWorkbench
      mode="draft"
      title={props.plan?.title || '场景设计稿'}
      subtitle="先按阶段和结局审阅场景结构，确认后再生成详细旁白与对话。"
      plan={props.plan}
      scenes={props.scenes}
      activeScene={activeDraftScene}
      setActiveScene={setActiveDraftScene}
      onScenesChange={(scenes) => props.onChange(scenes as GameDesignDraftScene[])}
      readonly={props.readonly}
      busy={props.busy}
      routeLabel={(scene) => draftSceneRouteLabel(scene as GameDesignDraftScene, props.plan)}
      markerLabel={(scene) => (scene.marker === 'Ending' ? '结局' : '场景')}
      inspector={
        <LaperInspectorShell
          eyebrow="信息"
          title="设计稿概览"
          stats={[
            { label: '场次', value: props.scenes.length },
            { label: '结局', value: props.scenes.filter((s) => s.marker === 'Ending').length },
            { label: '总行数', value: props.scenes.reduce((n, s) => n + s.lines.length, 0) },
          ]}
          note="确认场景结构与对白安排后，再生成详细旁白与对话。"
          footer={
            !props.readonly || props.retryAction ? (
              <>
                {!props.readonly ? (
                  <button
                    className="btn outline"
                    type="button"
                    disabled={props.busy || !props.dirty}
                    onClick={props.saveDesignDraft}
                  >
                    保存设计稿
                  </button>
                ) : null}
                <button
                  className={`btn primary ${props.retryAction ? 'retry-action' : ''}`}
                  type="button"
                  disabled={props.busy || (!props.retryAction && props.scenes.length === 0)}
                  onClick={props.retryAction || props.completeDesignDraft}
                >
                  {props.retryAction ? <span aria-hidden="true">↻</span> : null}
                  {props.busy && props.retryAction ? '正在重试...' : props.retryLabel || '确认并生成详细场景'}
                </button>
              </>
            ) : undefined
          }
        />
      }
    />
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
                  <button
                    className="btn outline"
                    type="button"
                    disabled={props.busy || !props.scenesDirty}
                    onClick={() => props.saveScenes(false)}
                  >
                    仅保存草稿
                  </button>
                  <button
                    className="btn primary"
                    type="button"
                    disabled={props.busy}
                    onClick={() => props.saveScenes(true)}
                  >
                    保存并应用到游戏
                  </button>
                </>
              ) : (
                <button
                  className="btn primary"
                  type="button"
                  disabled={props.busy}
                  onClick={() => props.saveScenes(false)}
                >
                  保存并生成素材
                </button>
              )
            ) : undefined
          }
        />
      }
    />
  );
}
