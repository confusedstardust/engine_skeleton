import { forgeApi as api } from '../../../lib/api-client';

import type { PersonalLibraryAsset, AssetReviewItem } from '../../../domain/assets';

import type { NodesResponse } from '../../../domain/jobs';

import { creditBalanceChangedEvent } from '../../../components/credit-balance';

import { assetDisplayName } from './workspace-assets';
type AssetActionContext = {
  notify?: (message: string, tone?: "info" | "success" | "error") => void;
  jobId: string;
  data: NodesResponse | null;
  setBusy: (value: boolean) => void;
  setMessage: (value: string) => void;
  setErrorMessage: (value: string) => void;
  refresh: (silent?: boolean) => Promise<void>;
  setAssetPromptDirty: (value: boolean) => void;
  setVoiceGeneratingSpeaker: (value: string | null) => void;
};
export function createJobAssetActions(context: AssetActionContext) {
  const { notify, jobId, data, setBusy, setMessage, setErrorMessage, refresh, setAssetPromptDirty, setVoiceGeneratingSpeaker } =
    context;
  async function regenerateAsset(asset: AssetReviewItem, prompt: string) {
    setBusy(true);
    setMessage(`正在重新生成素材：${asset.filename}`);
    try {
      await api(`/jobs/${jobId}/assets/regenerate`, {
        method: 'POST',
        body: JSON.stringify({
          filename: asset.filename,
          prompt,
          background: true,
          base_revision: data?.job.draft_revision ?? 0,
        }),
      });
      window.dispatchEvent(new Event(creditBalanceChangedEvent));
      setAssetPromptDirty(false);
      setMessage('单个素材已加入生成队列。');
      notify?.('单个素材已加入生成队列。', 'success');
      await refresh(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '重新生成素材失败。');
    } finally {
      setBusy(false);
    }
  }

  async function previewSceneMusic(asset: string): Promise<Blob> {
    return api.blob(`/jobs/${jobId}/music-library/${encodeURIComponent(asset)}`);
  }

  async function uploadAsset(
    file: File,
    assetType: 'image' | 'bgm',
    imageRole: 'figure' | 'background' = 'background',
    removeBackground = false,
    replaceFilename?: string,
  ): Promise<boolean> {
    setBusy(true);
    setMessage(removeBackground ? '正在上传并抠出立绘主体...' : `正在上传${assetType === 'bgm' ? ' BGM' : '图片'}...`);
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('asset_type', assetType);
      body.append('image_role', imageRole);
      body.append('remove_background', String(removeBackground));
      if (replaceFilename) body.append('replace_filename', replaceFilename);
      body.append('base_revision', String(data?.job.draft_revision ?? 0));
      await api(`/jobs/${jobId}/assets/upload`, { method: 'POST', body });
      setMessage(removeBackground ? '立绘已抠图并加入草稿素材。' : '素材已加入草稿，应用修改后会进入游戏。');
      await refresh(true);
      return true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '上传素材失败。');
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function loadLibraryAssets(
    kind: PersonalLibraryAsset['kind'],
    page: number,
    signal?: AbortSignal,
  ): Promise<{ assets: PersonalLibraryAsset[]; has_more: boolean }> {
    const params = new URLSearchParams({ kind, collection: 'personal', page: String(page), page_size: '6' });
    return api<{ assets: PersonalLibraryAsset[]; has_more: boolean }>(`/assets?${params}`, { signal });
  }

  async function useLibraryAsset(
    asset: PersonalLibraryAsset,
    target: 'figure' | 'background' | 'bgm',
    replaceFilename?: string,
  ): Promise<boolean> {
    setBusy(true);
    setMessage(`正在从素材库调用「${asset.name}」...`);
    try {
      await api(`/jobs/${jobId}/assets/from-library`, {
        method: 'POST',
        body: JSON.stringify({
          asset_file_id: asset.file_id,
          target,
          replace_filename: replaceFilename,
          base_revision: data?.job.draft_revision ?? 0,
        }),
      });
      setMessage(target === 'bgm' ? '素材库音乐已加入当前作品。' : '素材库图片已替换当前草稿素材。');
      notify?.(target === 'bgm' ? '素材库音乐已加入当前作品。' : '素材库图片已替换当前草稿素材。', 'success');
      await refresh(true);
      return true;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '调用素材库失败。');
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function removeAssetBackground(asset: AssetReviewItem): Promise<boolean> {
    setBusy(true);
    setMessage(`正在为 ${assetDisplayName(asset)} 抠图...`);
    try {
      await api(`/jobs/${jobId}/assets/remove-background`, {
        method: 'POST',
        body: JSON.stringify({ filename: asset.filename, base_revision: data?.job.draft_revision ?? 0 }),
      });
      setMessage('立绘背景已移除。');
      notify?.('立绘背景已移除。', 'success');
      await refresh(true);
      return true;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '一键抠图失败。');
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function previewCharacterVoice(speaker: string, voice: string) {
    setVoiceGeneratingSpeaker(speaker);
    setBusy(true);
    setMessage(`正在为 ${speaker} 生成新的音色试听...`);
    try {
      await api(`/jobs/${jobId}/voices/preview`, {
        method: 'POST',
        body: JSON.stringify({ speaker, voice }),
      });
      setMessage(`${speaker} 的新试听已生成，可以直接播放比较。`);
      notify?.(`${speaker} 的新试听已生成，可以直接播放比较。`, "success");
      await refresh(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '语音试听生成失败。');
    } finally {
      window.dispatchEvent(new Event(creditBalanceChangedEvent));
      setVoiceGeneratingSpeaker(null);
      setBusy(false);
    }
  }

  return {
    regenerateAsset,
    previewSceneMusic,
    uploadAsset,
    loadLibraryAssets,
    useLibraryAsset,
    removeAssetBackground,
    previewCharacterVoice,
  };
}
