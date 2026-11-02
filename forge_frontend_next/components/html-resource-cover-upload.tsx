'use client';
import { useState } from 'react';
import * as Dialog from './ui/dialog';
import { DialogHeader } from './ui/dialog-header';
import { DialogActions } from './ui/dialog-actions';
import { Button } from './ui/button';
import { AssetFileInput, UploadStatus } from './ui/file-upload';
import { useFileUpload } from '../hooks/use-file-upload';
import { useToast } from './ui/toast';
import { imageUploadPolicy, uploadPolicyHint } from '../lib/upload-policy';
import { adminApi } from '../lib/api-client';

const policy = { ...imageUploadPolicy, maxBytes: 5 * 1024 * 1024 };
export default function HtmlResourceCoverUpload({ identifier, title, onSaved }: { identifier: string; title: string; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const upload = useFileUpload();
  const notify = useToast();
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    const ok = await upload.run(file, policy, async () => {
      const data = new FormData(); data.set('file', file);
      const result = await adminApi<{cover_status: string; cover_error?: string}>(`/html-resources/${identifier}/cover`, { method: 'POST', body: data });
      if (result.cover_status === 'sync_failed') throw new Error(result.cover_error || '封面已保存，广场同步失败');
    });
    onSaved();
    if (ok) { notify('封面已替换', 'success'); setOpen(false); setFile(null); }
  }
  return <Dialog.Root open={open} onOpenChange={value => { setOpen(value); if (value) { setFile(null); upload.setError(''); } }} busy={upload.pending}>
    <Dialog.Trigger asChild><Button>替换封面</Button></Dialog.Trigger>
    <Dialog.Surface className="admin-detail" aria-describedby={undefined}>
      <DialogHeader dialogTitle title="替换资源封面" subtitle={title} onClose={() => setOpen(false)} busy={upload.pending} />
      <form onSubmit={submit}><fieldset disabled={upload.pending} style={{border: 0, padding: 0}}>
        <p>将裁切为 16:9 封面，建议选择横向图片。{uploadPolicyHint(policy)}</p>
        <AssetFileInput policy={policy} aria-label="选择封面图片" onFileSelected={setFile} onValidationError={message => {setFile(null); upload.setError(message);}} />
        <UploadStatus pending={upload.pending} error={upload.error} />
        <DialogActions><Button onClick={() => setOpen(false)}>取消</Button><Button variant="primary" type="submit" busy={upload.pending} disabled={!file}>保存封面</Button></DialogActions>
      </fieldset></form>
    </Dialog.Surface>
  </Dialog.Root>;
}
