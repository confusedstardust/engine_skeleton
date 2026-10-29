'use client';
import { EmptyState } from '../../../components/ui/state';
import { InlineFeedback } from '../../../components/ui/feedback';

import { Button } from '../../../components/ui/button';
import { WorkbenchHeader } from '../../../components/workbench-header';
import type { MouseEvent } from 'react';

import { use } from 'react';

import { SceneScrollButton } from '../../../components/scene-scroll-button';

import { withBasePath } from '../../base-path';
import { useJobWorkspace } from './use-job-workspace';
import { CompletionPanel } from './completion-panel';
import { AssetReviewPanel } from './asset-review-panel';
import { OutlineEditor, SceneGenerationStatus, SceneEditor } from './workspace-editors';

export default function JobWorkspacePage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  return <JobWorkspace key={jobId} jobId={jobId} />;
}

function JobWorkspace({ jobId }: { jobId: string }) {
  const {
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
  } = useJobWorkspace(jobId);

  const handleNavigation = async (event: MouseEvent<HTMLAnchorElement>) => {
    if (!(planDirty || scenesDirty || assetPromptDirty)) return;
    event.preventDefault();
    const target = event.currentTarget.href;
    if (await confirm('还有未保存的修改，确定离开吗？')) window.location.assign(target);
  };

  if (!data) {
    return (
      <main className="main-wrapper">
        <EmptyState as="section" className="workspace-empty">
          <h1>生成工作台</h1>
          <p>{message}</p>
        </EmptyState>
      </main>
    );
  }

  return (
    <>
      <WorkbenchHeader
        title="临场 · 生成工作台"
        label="任务导航"
        returnHref="/history"
        onNavigate={handleNavigation}
      />

      <main className="main-wrapper workspace-wrapper">
        <section className="workflow-head">
          <div>
            <span className={`status-pill ${data.job.status.toLowerCase()}`}>{data.job.status}</span>
            <h1>
              {stage === 'outline'
                ? '确认故事大纲'
                : stage === 'scenes'
                ? '审阅场景文本'
                : stage === 'assets'
                ? '审阅素材资产'
                : '游戏生成完成'}
            </h1>
            {stage !== 'complete' ? (
              <p>
                {stage === 'outline'
                  ? '先确认阶段数量和角色阵容。这里的删改会影响下一阶段生成的场景。'
                  : stage === 'scenes'
                  ? '按场景逐个审阅旁白、对话和分支内容，保存后会进入素材规划和生成。'
                  : '按角色和场景检查素材规划、生成图片和提示词，不满意的单个资产可以重新生成。'}
              </p>
            ) : null}
          </div>
          <div className="workflow-steps">
            <Button variant="unstyled" className={stage === 'outline' ? 'active' : ''} type="button" onClick={() => setStage('outline')}>
              1 大纲
            </Button>
            <Button variant="unstyled"
              className={stage === 'scenes' ? 'active' : ''}
              type="button"
              onClick={() => setStage('scenes')}
              disabled={!canOpenScenes}
            >
              2 场景
            </Button>
            <Button variant="unstyled"
              className={stage === 'assets' ? 'active' : ''}
              type="button"
              onClick={() => setStage('assets')}
              disabled={!canOpenAssets}
            >
              3 素材
            </Button>
            <Button variant="unstyled"
              className={stage === 'complete' ? 'active' : ''}
              type="button"
              onClick={() => setStage('complete')}
              disabled={!hasPublishedBuild}
            >
              4 完成
            </Button>
          </div>
        </section>

        {editScope !== 'none' ? (
          <div className="draft-edit-banner">
            <div>
              <strong>草稿编辑中</strong>
              <span>当前可玩版本不会立即改变；点击应用后，只同步实际修改过的内容。</span>
            </div>
            <Button variant="outline" type="button" onClick={exitCompletedEdit}>
              退出编辑
            </Button>
          </div>
        ) : null}

        {(failedRetry || data.job.error || operationError || Object.keys(connectionErrors).length > 0) && (
          <InlineFeedback as="div" className="workspace-status workflow-status failed" >
            <strong>{failedRetry ? '生成失败 · 可重试' : '需要处理'}</strong>
            <span>
              {data.job.error || (operationError ? message : '部分场景的连接需要修正，请查看红色标记和对应错误提示。')}
            </span>
          </InlineFeedback>
        )}

        {sceneConnectionReport?.status === 'failed' && sceneConnectionReport.errors.length > 0 ? (
          <details className="connection-check-panel failed" open>
            <summary>
              <strong>场景连接需要处理</strong>
              <span>发现 {sceneConnectionReport.errors.length} 处连接问题</span>
            </summary>
            {sceneConnectionReport.errors.length > 0 ? (
              <ul>
                {sceneConnectionReport.errors.map((error, index) => (
                  <li key={`${error.code}-${error.scene_file}-${index}`}>
                    {error.scene_file ? `${error.scene_file}：` : ''}
                    {error.message}
                  </li>
                ))}
              </ul>
            ) : null}
          </details>
        ) : null}

        {stage === 'scenes' && <SceneScrollButton />}

        {stage === 'complete' ? (
          <CompletionPanel
            job={data.job}
            playUrl={withBasePath(`/play/${data.job.id}/`)}
            busy={busy}
            editDraft={beginCompletedEdit}
          />
        ) : stage === 'outline' ? (
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
            retryAction={failedRetry?.stage === 'outline' ? retryFailedPhase : undefined}
            retryLabel={failedRetry?.stage === 'outline' ? failedRetry.label : undefined}
          />
        ) : stage === 'assets' ? (
          <AssetReviewPanel
            review={assetReview}
            busy={busy || isGenerating}
            activeAsset={activeAsset}
            assetPrompt={assetPrompt}
            setAssetPrompt={(value) => {
              setAssetPrompt(value);
              setAssetPromptDirty(true);
            }}
            openAsset={(asset) => {
              setActiveAssetFilename(asset.filename);
              setAssetPrompt(asset.prompt || '');
              setAssetPromptDirty(false);
            }}
            closeAsset={async () => {
              if (assetPromptDirty && !(await confirm('Prompt 还没有用于重新生成素材，确定返回列表吗？'))) return;
              setAssetPromptDirty(false);
              setActiveAssetFilename(null);
            }}
            regenerateAsset={regenerateAsset}
            previewVoice={previewCharacterVoice}
            voiceGeneratingSpeaker={voiceGeneratingSpeaker}
            buildGame={buildGameFromAssets}
            sceneMusic={assetReview?.scene_music || []}
            musicAssets={assetReview?.music_assets || []}
            musicAssetNames={assetReview?.music_asset_names}
            sceneMusicEnabled={!autoMode}
            previewSceneMusic={previewSceneMusic}
            particleEffects={assetReview?.particle_effects || { effects: [], scenes: [] }}
            uploadAsset={uploadAsset}
            loadLibraryAssets={loadLibraryAssets}
            useLibraryAsset={useLibraryAsset}
            removeAssetBackground={removeAssetBackground}
            gameReady={hasPublishedBuild}
            buildState={data.job.build_state || 'CURRENT'}
            hasDraftChanges={
              (data.job.draft_revision ?? 0) > (data.job.published_revision ?? 0) || data.job.build_state === 'STALE'
            }
            assetsGenerating={isAssetGenerationRunning}
            gameBuilding={isGameBuildRunning}
            readonly={assetsLocked}
            playUrl={withBasePath(`/play/${data.job.id}/`)}
            retryAction={failedRetry?.stage === 'assets' ? retryPhase : undefined}
            retryLabel={failedRetry?.stage === 'assets' ? failedRetry.label : undefined}
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
            connectionErrors={connectionErrors}
            setActiveScene={setActiveScene}
            updateScene={updateScene}
            setScenes={setScenes}
            setScenesDirty={setScenesDirty}
            saveScenes={saveScenes}
            published={hasPublishedBuild}
          />
        ) : (
          <SceneGenerationStatus
            busy={busy || isGenerating}
            generatingCompletion={isDesignCompletionRunning}
            resumeAction={data.job.status === 'GAME_DESIGN_DRAFT_READY' && !isGenerating && !autoMode ? continueSceneGeneration : undefined}
            retryAction={failedRetry?.stage === 'scenes' ? retryFailedPhase : undefined}
            retryLabel={failedRetry?.stage === 'scenes' ? failedRetry.label : undefined}
          />
        )}
      </main>
    </>
  );
}
