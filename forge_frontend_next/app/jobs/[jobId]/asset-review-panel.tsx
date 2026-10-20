'use client';

import type {
  PersonalLibraryAsset,
  StagedScenePresentation,
  AssetReviewItem,
  AssetReviewResponse,
  SceneMusicItem,
  ParticleEffectReview,
} from '../../../domain/assets';

import { LaperAssetWorkbench } from '../../../components/laper-asset-workbench';

import { LoadingPlaceholder, FailedPlaceholder } from './workspace-placeholders';
import { assetDisplayName, assetSceneDisplayName } from './workspace-assets';

export function AssetReviewPanel(props: {
  review: AssetReviewResponse | null;
  busy: boolean;
  activeAsset: AssetReviewItem | null;
  assetPrompt: string;
  setAssetPrompt: (value: string) => void;
  openAsset: (asset: AssetReviewItem) => void;
  closeAsset: () => void;
  regenerateAsset: (asset: AssetReviewItem, prompt: string) => Promise<void>;
  previewVoice: (speaker: string, voice: string) => Promise<void>;
  voiceGeneratingSpeaker: string | null;
  buildGame: (staged?: StagedScenePresentation) => Promise<boolean>;
  sceneMusic: SceneMusicItem[];
  musicAssets: string[];
  musicAssetNames?: Record<string, string>;
  sceneMusicEnabled: boolean;
  previewSceneMusic: (asset: string) => Promise<Blob>;
  particleEffects: ParticleEffectReview;
  uploadAsset: (
    file: File,
    assetType: 'image' | 'bgm',
    imageRole?: 'figure' | 'background',
    removeBackground?: boolean,
    replaceFilename?: string,
  ) => Promise<boolean>;
  loadLibraryAssets: (
    kind: PersonalLibraryAsset['kind'],
    page: number,
    signal?: AbortSignal,
  ) => Promise<{ assets: PersonalLibraryAsset[]; has_more: boolean }>;
  useLibraryAsset: (
    asset: PersonalLibraryAsset,
    target: 'figure' | 'background' | 'bgm',
    replaceFilename?: string,
  ) => Promise<boolean>;
  removeAssetBackground: (asset: AssetReviewItem) => Promise<boolean>;
  gameReady: boolean;
  buildState: string;
  hasDraftChanges: boolean;
  assetsGenerating: boolean;
  gameBuilding: boolean;
  readonly: boolean;
  playUrl: string;
  retryAction?: (staged?: StagedScenePresentation) => Promise<boolean>;
  retryLabel?: string;
}) {
  const assets = props.review?.assets || [];

  if (props.assetsGenerating) {
    return (
      <section className="node-detail">
        <LoadingPlaceholder
          title="素材正在生成。"
          brief="系统正在生成角色和场景图片；开启配音时，还会为每位角色生成一句语音试听。完成后可直接在角色卡播放并按需更换音色。"
        />
      </section>
    );
  }

  if (props.gameBuilding) {
    return (
      <section className="node-detail">
        <LoadingPlaceholder
          title="游戏正在生成。"
          brief="系统正在把素材、脚本、音效和配音写入 WebGAL 游戏目录，完成后会自动显示打开游戏入口。"
        />
      </section>
    );
  }

  if (!props.review || assets.length === 0) {
    return (
      <section className="node-detail">
        {props.retryAction ? (
          <FailedPlaceholder
            title="素材阶段生成失败。"
            brief="自动重试仍未完成这一阶段，可以从失败的阶段重新生成。"
            action={() => void props.retryAction?.()}
            actionLabel={props.retryLabel || '重试生成素材'}
            busy={props.busy}
          />
        ) : (
          <LoadingPlaceholder
            title="素材规划还在生成。"
            brief="场景保存后会自动进入素材阶段，完成后这里会展示角色卡和场景卡。"
          />
        )}
      </section>
    );
  }

  return (
    <LaperAssetWorkbench
      imageEnabled={props.review.image_enabled}
      assets={assets}
      voiceEnabled={props.review.voice_enabled}
      voices={props.review.voices || []}
      availableVoices={props.review.available_voices || []}
      busy={props.busy}
      readonly={props.readonly}
      published={props.gameReady}
      buildState={props.buildState}
      hasDraftChanges={props.hasDraftChanges}
      activeAsset={props.activeAsset}
      assetPrompt={props.assetPrompt}
      setAssetPrompt={props.setAssetPrompt}
      openAsset={props.openAsset}
      closeAsset={props.closeAsset}
      regenerateAsset={props.regenerateAsset}
      previewVoice={props.previewVoice}
      voiceGeneratingSpeaker={props.voiceGeneratingSpeaker}
      sceneMusic={props.sceneMusic}
      musicAssets={props.musicAssets}
      musicAssetNames={props.musicAssetNames}
      sceneMusicEnabled={props.sceneMusicEnabled}
      previewSceneMusic={props.previewSceneMusic}
      particleEffects={props.particleEffects}
      uploadAsset={props.uploadAsset}
      loadLibraryAssets={props.loadLibraryAssets}
      useLibraryAsset={props.useLibraryAsset}
      removeAssetBackground={props.removeAssetBackground}
      buildGame={props.buildGame}
      retryAction={props.retryAction}
      retryLabel={props.retryLabel}
      displayName={assetDisplayName}
      sceneDisplayName={assetSceneDisplayName}
    />
  );
}
