'use client';
import { Button } from './ui/button';
import { useToast } from "./ui/toast";
import * as Dialog from './ui/dialog';
import * as ToggleGroup from '@radix-ui/react-toggle-group';
import * as Tabs from '@radix-ui/react-tabs';
import { useEffect, useState } from 'react';
import { attributeGroups } from './asset-attribute-groups';
import { useFileUpload } from '../hooks/use-file-upload';
import { AssetFileInput, UploadStatus } from './ui/file-upload';
import { imageUploadPolicy, adminMusicUploadPolicy, uploadPolicyHint } from '../lib/upload-policy';
import { adminApi } from '../lib/api-client';
type Vocabulary = Record<string, { attributes: Record<string, string[]> }>;
const kinds = [
  { value: 'BACKGROUND', label: '背景' },
  { value: 'FIGURE', label: '立绘' },
  { value: 'BGM', label: 'BGM' },
];
export default function AdminAssetUpload({ onUploaded }: { onUploaded: () => void }) {
  const upload = useFileUpload();
  const busy = upload.pending;
  const notify = useToast();
  const [open, setOpen] = useState(false),
    [filename, setFilename] = useState('');
  const [kind, setKind] = useState('BACKGROUND'),
    [attributes, setAttributes] = useState<Record<string, string[]>>({}),
    [message, setMessage] = useState('');
  const policy = kind === 'BGM' ? adminMusicUploadPolicy : imageUploadPolicy;
  const [vocabulary, setVocabulary] = useState<Vocabulary>({}),
    [drafts, setDrafts] = useState<Record<string, string>>({}),
    [adding, setAdding] = useState('');
  useEffect(() => {
    if (!open) return;
    let active = true;
    adminApi<Vocabulary>('/assets/taxonomy')
      .then((data) => {
        if (active)
          setVocabulary((old) => {
            const next = { ...old };
            for (const k of kinds) {
              const values = { ...(old[k.value]?.attributes || {}) };
              for (const [key, options] of Object.entries(data[k.value]?.attributes || {}))
                values[key] = Array.from(new Set([...(values[key] || []), ...(options as string[])]));
              next[k.value] = { attributes: values };
            }
            return next;
          });
      })
      .catch((e) => {
        if (active) setMessage(e.message);
      });
    return () => {
      active = false;
    };
  }, [open]);
  function choose(key: string, values: string[]) {
    setAttributes((old) => ({ ...old, [key]: values }));
  }
  function addChoice(key: string, multiple: boolean) {
    const text = (drafts[key] || '').trim();
    if (!text) return;
    setVocabulary((old) => ({
      ...old,
      [kind]: {
        attributes: {
          ...(old[kind]?.attributes || {}),
          [key]: Array.from(new Set([...(old[kind]?.attributes?.[key] || []), text])),
        },
      },
    }));
    choose(key, multiple ? Array.from(new Set([...(attributes[key] || []), text])) : [text]);
    setDrafts((old) => ({ ...old, [key]: '' }));
    setAdding('');
  }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const file = data.get('file');
    if (!(file instanceof File)) {
      upload.setError('请选择素材文件');
      return;
    }
    data.set('kind', kind);
    data.set('attributes', JSON.stringify(attributes));
    setMessage('');
    const ok = await upload.run(file, policy, async () => {
      await adminApi('/assets/upload', { method: 'POST', body: data });
    });
    if (ok) {
      form.reset();
      setFilename('');
      setAttributes({});
      notify('上传成功，已加入公共素材库', 'success');
      onUploaded();
      setOpen(false);
    }
  }
  return (
    <Dialog.Root
      busy={busy}
      open={open}
      onOpenChange={(value) => {
        if (!busy) {
          setOpen(value);
          if (value) {
            setMessage('');
            upload.setError('');
          }
        }
      }}
    >
      <div className="admin-upload-entry">
        <Dialog.Trigger asChild>
          <Button variant="outline" type="button">
            <span aria-hidden="true">＋</span> 上传公共素材
          </Button>
        </Dialog.Trigger>
      </div>
      <Dialog.Surface
        overlayClassName="radix-confirm-overlay"
        className="admin-upload-dialog"
        aria-describedby="admin-upload-description"
        onEscapeKeyDown={(e) => {
          if (busy) e.preventDefault();
        }}
        onPointerDownOutside={(e) => {
          if (busy) e.preventDefault();
        }}
      >
        <header className="asset-modal-head">
          <Dialog.Title>上传公共素材</Dialog.Title>
          <Dialog.Close asChild>
            <button type="button" aria-label="关闭上传" disabled={busy}>
              ×
            </button>
          </Dialog.Close>
        </header>
        <form onSubmit={submit}>
          <div className="admin-upload-body">
            <Dialog.Description id="admin-upload-description">
              添加到平台素材库，供用户浏览、收藏和选用。
            </Dialog.Description>
            <fieldset disabled={busy}>
              <Tabs.Root
                value={kind}
                onValueChange={(v) => {
                  setKind(v);
                  setAttributes({});
                  setFilename('');
                  setDrafts({});
                  setAdding('');
                  upload.setError('');
                  setMessage('');
                }}
              >
                <Tabs.List className="admin-upload-types" aria-label="素材类型">
                  {kinds.map((k) => (
                    <Tabs.Trigger key={k.value} value={k.value} disabled={busy}>
                      {k.label}
                    </Tabs.Trigger>
                  ))}
                </Tabs.List>
              </Tabs.Root>
              <div className="admin-upload-fields">
                <label className="admin-upload-name">
                  素材名称
                  <input name="name" placeholder="输入用户看到的素材名称" required maxLength={200} />
                </label>
              </div>
              <label className="admin-upload-file">
                <AssetFileInput
                  key={kind}
                  name="file"
                  required
                  disabled={busy}
                  aria-label="选择素材文件"
                  policy={policy}
                  onFileSelected={(file) => {
                    setFilename(file.name);
                    setMessage('');
                  }}
                  onValidationError={(error) => {
                    upload.setError(error);
                    if (error) setFilename('');
                  }}
                />
                <span className="admin-upload-file-icon" aria-hidden="true">
                  ↑
                </span>
                <strong>{filename || '点击选择文件'}</strong>
                <span>{uploadPolicyHint(policy)}</span>
              </label>
              <section className="admin-attribute-section" aria-label="素材属性">
                <div className="admin-upload-tag-heading">
                  素材属性<span>按需填写</span>
                </div>
                {(attributeGroups[kind] || []).map((group) => {
                  const options = Array.from(
                    new Set([...group.options, ...(vocabulary[kind]?.attributes?.[group.key] || [])]),
                  );
                  const items = options.map((value) => (
                    <ToggleGroup.Item key={value} value={value}>
                      {value}
                    </ToggleGroup.Item>
                  ));
                  return (
                    <div className="admin-attribute-row" key={group.key}>
                      <div className="admin-attribute-label">
                        <strong>{group.label}</strong>
                        <span>{group.multiple ? '多选' : '单选'}</span>
                      </div>
                      <div className="admin-attribute-options">
                        {group.multiple ? (
                          <ToggleGroup.Root
                            className="admin-upload-tags"
                            type="multiple"
                            value={attributes[group.key] || []}
                            onValueChange={(v) => choose(group.key, v)}
                            disabled={busy}
                            aria-label={group.label}
                          >
                            {items}
                          </ToggleGroup.Root>
                        ) : (
                          <ToggleGroup.Root
                            className="admin-upload-tags"
                            type="single"
                            value={attributes[group.key]?.[0] || ''}
                            onValueChange={(v) => choose(group.key, v ? [v] : [])}
                            disabled={busy}
                            aria-label={group.label}
                          >
                            {items}
                          </ToggleGroup.Root>
                        )}
                        {adding === group.key ? (
                          <div className="admin-upload-add">
                            <input
                              autoFocus
                              value={drafts[group.key] || ''}
                              maxLength={40}
                              aria-label={`新增${group.label}`}
                              placeholder={`添加${group.label}选项`}
                              onChange={(e) => setDrafts((old) => ({ ...old, [group.key]: e.target.value }))}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  e.preventDefault();
                                  addChoice(group.key, group.multiple);
                                }
                              }}
                            />
                            <Button
                              variant="outline"
                              type="button"
                              busy={Boolean(busy)} disabled={busy || !drafts[group.key]?.trim()}
                              onClick={() => addChoice(group.key, group.multiple)}
                            >
                              添加
                            </Button>
                            <Button variant="outline" type="button" onClick={() => setAdding('')}>
                              取消
                            </Button>
                          </div>
                        ) : (
                          <button
                            className="admin-attribute-add"
                            type="button"
                            disabled={busy}
                            onClick={() => setAdding(group.key)}
                          >
                            ＋ 添加{group.label}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </section>
            </fieldset>
            <UploadStatus
              pending={busy}
              error={upload.error || message}
              message="正在上传素材…"
              className="admin-upload-message"
            />
          </div>
          <footer className="asset-modal-actions">
            <Dialog.Close asChild>
              <Button variant="outline" type="button" busy={Boolean(busy)}>
                取消
              </Button>
            </Dialog.Close>
            <Button variant="primary" type="submit" busy={Boolean(busy)}>
              {busy ? '正在上传…' : '上传素材'}
            </Button>
          </footer>
        </form>
      </Dialog.Surface>
    </Dialog.Root>
  );
}
