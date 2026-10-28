'use client';
import { useRef, useState } from 'react';
import { forgeApi as api } from '../lib/api-client';
import type { Job } from '../domain/jobs';
import type { PersonalLibraryAsset } from '../domain/assets';
import { AssetSourceActions, AssetDialogActions } from './assets/asset-dialog-actions';
import { AssetFileInput } from './ui/file-upload';
import { imageUploadPolicy } from '../lib/upload-policy';
import { AssetPickerDialog } from './assets/asset-picker-dialog';
import { ContentDialog } from './ui/content-dialog';
import { ImagePreview } from './ui/image-preview';
import { withBasePath } from '../app/base-path';

export function EditCoverDialog({ job, onClose, onSaved }: { job: Job; onClose: () => void; onSaved: (job: Job) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [library, setLibrary] = useState(false);
  async function save(body: FormData | string, fromLibrary = false) {
    if (lock.current) return false;
    lock.current = true; setBusy(true); setError('');
    try {
      const result = await api<{ job: Job }>(`/jobs/${job.id}/assets/${fromLibrary ? 'from-library' : 'upload'}`, { method: 'POST', body });
      onSaved(result.job);
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '封面更新失败，请重试');
      throw reason;
    } finally { lock.current = false; setBusy(false); }
  }
  if (library) return <AssetPickerDialog<PersonalLibraryAsset>
    title="选择游戏封面"
    load={(page, signal) => api(`/assets?kind=BACKGROUND&collection=personal&page=${page}&page_size=6`, { signal })}
    onClose={() => setLibrary(false)}
    onSelect={asset => save(JSON.stringify({ asset_file_id: asset.file_id, target: 'background', title_cover: true, base_revision: job.draft_revision }), true)}
  />;
  return <ContentDialog title="编辑封面" busy={busy} onClose={onClose} className="history-cover-dialog" bodyClassName="cover-dialog-body" closeInHeader={false} footer={<AssetDialogActions busy={busy} onClose={onClose} />}>
      <p>同时更新游戏启动背景和作品封面。建议使用 16:9 横图。</p>
      <ImagePreview className="history-cover-preview" src={withBasePath(`/play/${job.id}/cover?revision=${job.published_revision ?? 0}&cover=${job.cover_revision ?? 0}`)} alt="当前游戏封面" fallback="无封面" />
      <AssetFileInput ref={input} hidden policy={imageUploadPolicy} resetAfterSelect onValidationError={setError} onFileSelected={async file => {
        const data = new FormData(); data.set('file', file); data.set('asset_type', 'image'); data.set('image_role', 'background'); data.set('title_cover', 'true');
        if (job.draft_revision !== undefined) data.set('base_revision', String(job.draft_revision));
        await save(data);
      }} />
      {error && <p role="alert">{error}</p>}
      <AssetSourceActions busy={busy} onUpload={() => input.current?.click()} onLibrary={() => setLibrary(true)} />
  </ContentDialog>;
}
